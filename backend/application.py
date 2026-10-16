"""Application use cases. HTTP handlers call this boundary, never feature storage."""
import asyncio
from dataclasses import asdict
import logging
import math
import hashlib
import json
import re
import uuid

from . import __version__
from .contracts.recommendation import ScoreCandidate, ScoreRequest, ScoreTerm
from .candidate.rounds import validate_options
from .domain import GoneError, NotFoundError, ValidationError, feedback_value, generation_count, generation_fields
from .events import EventHub
from .store.contracts import Storage
from .store.roam_settings import max_history_images, prefetch_count, selection


def public_backend(config):
    result = {key: value for key, value in config.items() if key != "api_key"}
    result["has_api_key"] = bool(config.get("api_key"))
    return result


class PictideApplication:
    def __init__(self, paths, storage: Storage, tasks, candidates, recommendation,
                 history, cleanup, workflows, roam, recommendation_store=None):
        self.paths, self.storage, self.tasks = paths, storage, tasks
        self.candidates, self.recommendation = candidates, recommendation
        self.history, self.cleanup, self.workflows = history, cleanup, workflows
        self.recommendation_store = recommendation_store
        self._recommendation_error = None
        self.roam = roam
        self._roam_lock = asyncio.Lock()
        self.events = EventHub()
        self.tasks.on_change = lambda: self.events.publish("jobs")

    async def start(self, session):
        self.tasks.session = self.tasks.connections.session = session
        await asyncio.to_thread(self._sync_recommendation)
        await self.cleanup.maybe_cleanup(force=True)
        await self.tasks.start()

    async def stop(self):
        await self.tasks.stop()

    async def clean_history(self, force=False, *, roam_only=False):
        before = self.cleanup.stats.get("revision", 0)
        result = await self.cleanup.maybe_cleanup(force=force, roam_only=roam_only)
        if self.cleanup.stats.get("revision", 0) != before:
            self.events.publish("artifacts")
        return result

    def _sync_recommendation(self):
        """Drain durable feedback at existing application entry points."""
        status = self.recommendation.status()
        self._recommendation_error = status.error
        if not status.available or self.recommendation_store is None:
            return status
        try:
            self.recommendation_store.seed_feedback("local", status.feature_version)
            for update in self.recommendation_store.pending_feedback("local", status.feature_version):
                result = self.recommendation.apply_feedback(update)
                if result.status == "pending":
                    self._recommendation_error = "推荐学习暂不可用，反馈已保存，将在下次操作重试。"
                    break
        except Exception:
            logging.getLogger(__name__).exception("Recommendation feedback remains pending")
            self._recommendation_error = "推荐学习暂不可用，反馈已保存，将在下次操作重试。"
        return status

    async def _learning_available(self):
        status = await asyncio.to_thread(self.recommendation.status)
        return status.available and not self._recommendation_error

    async def bootstrap(self):
        await self.clean_history()
        view = await asyncio.to_thread(self.storage.roam_view)
        page = await asyncio.to_thread(self.storage.artifact_page, source="roam", around=view["artifact_id"])
        recommendation = await asyncio.to_thread(self.recommendation.status)
        return {"name": "Pictide", "module": "pictide-web", "version": __version__,
                "database_path": str(self.storage.path), "data_directory": str(self.paths.root),
                "backend_types": self.tasks.connections.backend_types(),
                "backends": [public_backend(config) for config in await asyncio.to_thread(self.storage.backends)],
                "jobs": await self.list_jobs(), "artifacts": page["artifacts"],
                "roam_view": view,
                "artifact_revision": page["revision"], "counts": page["counts"],
                "artifact_page": {key: page[key] for key in ("has_more", "has_newer", "anchor_id", "next_cursor", "total", "revision")},
                "recommendation": asdict(recommendation) | {"error": self._recommendation_error or recommendation.error},
                "capabilities": {"generation": True, "feedback": True, "preference_learning": await self._learning_available(),
                                 "cooccurrence_prompts": True, "prompt_sequences": True, "events": True, "roam_prefetch": True}}

    async def preferences(self, page="1"):
        if not isinstance(page, str) or not re.fullmatch(r"[0-9]+", page):
            raise ValidationError("页码必须是正整数。")
        digits = page.lstrip("0")
        if not digits or len(digits) > 16 or int(digits) > 2**53 - 1:
            raise ValidationError("页码必须是 1 至 9007199254740991 的整数。")
        return asdict(await asyncio.to_thread(self.recommendation.preferences, "local", int(digits)))

    async def reset_preferences(self, payload):
        if set(payload) != {"request_id", "expected_reset_revision"}:
            raise ValidationError("需要 request_id 和 expected_reset_revision。")
        request_id, revision = payload["request_id"], payload["expected_reset_revision"]
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
            raise ValidationError("重置请求标识无效。")
        if isinstance(revision, bool) or not isinstance(revision, int) or not 0 <= revision <= 2**53 - 1:
            raise ValidationError("重置修订必须是非负整数。")
        # Drain a durable write on cancellation without routing recommendation
        # through the task module. Retrying keeps the same request identity.
        pending = asyncio.create_task(asyncio.to_thread(self.recommendation.reset_preferences,
            "local", request_id, revision))
        try:
            result = await asyncio.shield(pending)
        except asyncio.CancelledError:
            await pending
            self.events.publish("recommendation")
            raise
        self._recommendation_error = None
        self.events.publish("recommendation")
        return asdict(result)

    async def connection_draft(self, identifier, payload):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
            raise ValidationError("后端 ID 只能包含字母、数字、下划线和横线。")
        draft = dict(payload)
        old = await asyncio.to_thread(self.storage.backend, identifier)
        if "api_key" not in draft and old:
            draft["api_key"] = old.get("api_key", "")
        draft["id"] = identifier
        draft.pop("has_api_key", None)
        return draft

    async def save_backend(self, identifier, payload):
        draft = await self.connection_draft(identifier, payload)
        draft = await self.tasks.connections.resolve_connection(draft)
        if draft["workflow_mode"] == "custom" and any(
                key in payload for key in ("workflow_name", "workflow_id", "workflow_revision")):
            document = {key: draft[key] for key in ("workflow", "bindings", "output_nodes")}
            document["name"] = payload.get("workflow_name")
            document.update({key: payload[key] for key in ("workflow_id", "workflow_revision") if key in payload})
            saved = await asyncio.to_thread(self.workflows.save_and_apply, document, draft, self.storage.save_backend)
            self.events.publish("workflows")
        else:
            saved = await asyncio.to_thread(self.storage.save_backend, draft)
        self.events.publish("backends")
        return public_backend(saved)

    async def check_backend(self, identifier, payload):
        return await self.tasks.connections.check_connection(await self.connection_draft(identifier, payload))

    async def delete_backend(self, identifier, payload):
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
            raise ValidationError("后端 ID 只能包含字母、数字、下划线和横线。")
        if not await asyncio.to_thread(self.storage.delete_backend, identifier):
            raise NotFoundError("后端配置已不存在。")
        self.events.publish("backends")
        return {"deleted": True, "id": identifier}

    async def models(self, identifier, payload):
        return await self.tasks.connections.models(await self.connection_draft(identifier, payload))

    async def workflow_template(self, identifier, payload):
        result = await self.tasks.connections.template(await self.connection_draft(identifier, payload))
        return public_backend(result)

    async def list_jobs(self):
        return await asyncio.to_thread(self.storage.jobs)

    async def job_page(self, page):
        if not isinstance(page, str) or not re.fullmatch(r"[0-9]+", page):
            raise ValidationError("页码必须是正整数。")
        digits = page.lstrip("0")
        if not digits or len(digits) > 16 or int(digits) > 2**53 - 1:
            raise ValidationError("页码必须是 1 至 9007199254740991 的整数。")
        return await asyncio.to_thread(self.storage.job_page, int(digits))

    async def submit_job(self, payload):
        if "repetitions" in payload or "candidate" in payload:
            result = await self._submit_generation_plan(payload)
        else:
            fields = generation_fields(payload)
            count = generation_count(payload.get("count", 1))
            jobs = await self.tasks.database(self.storage.create_jobs, fields, count)
            result = {"job": jobs[0], "jobs": jobs, "next_seed": -1 if fields["seed"] == -1 else (fields["seed"] + count) % 2**53,
                      "candidate_result": None, "next_candidate": None}
        self.tasks.wake.set()
        self.events.publish("jobs")
        await self.clean_history()
        return result

    async def _submit_generation_plan(self, payload):
        count = generation_count(payload.get("count", 1))
        repetitions = payload.get("repetitions", 1)
        if type(repetitions) is not int or not 1 <= repetitions <= 10:
            raise ValidationError("生成次数必须是 1 至 10 的整数。")
        candidate = validate_options(payload["candidate"]) if "candidate" in payload else None
        fields = generation_fields({**payload, **({"positive": "pending candidate", "negative": ""} if candidate else {})})
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        previous = await asyncio.to_thread(self.storage.generation_plan, fields["request_id"], digest)
        if previous is not None:
            return previous
        backend = await asyncio.to_thread(self.storage.backend, fields["backend_id"])
        if backend is None:
            raise ValidationError("生图后端不存在，请先保存后端配置。")
        validated = self.tasks.connections.validate(backend)
        if candidate:
            rounds, next_candidate = await asyncio.to_thread(self.candidates.prepare_rounds, candidate, repetitions)
        else:
            rounds = [{"positive": fields["positive"], "negative": fields["negative"]}] * repetitions
            next_candidate = None
        plans = []
        for round_result in rounds:
            if round_result["negative"] and not validated.get("bindings", {}).get("negative"):
                raise ValidationError("当前后端未绑定负向输入，请清空负向提示词或配置负向绑定。")
            for _ in range(count):
                index = len(plans)
                plan = {**fields, "positive": round_result["positive"], "negative": round_result["negative"],
                        "request_id": fields["request_id"] if index == 0 else "round-" + uuid.uuid4().hex,
                        "seed": -1 if fields["seed"] == -1 else (fields["seed"] + index) % 2**53}
                plans.append(generation_fields(plan))
        context = {"next_seed": -1 if fields["seed"] == -1 else (fields["seed"] + len(plans)) % 2**53,
                   "candidate_result": rounds[-1] if candidate else None, "next_candidate": next_candidate}
        return await self.tasks.database(self.storage.commit_generation_plan, fields["request_id"], digest, plans, context, backend)

    async def cancel_pending_jobs(self, payload):
        if payload:
            raise ValidationError("批量取消请求不接受额外参数，仅取消生成页待执行任务。")
        return {"cancelled_count": await self.tasks.cancel_pending()}

    async def cancel_job(self, identifier):
        job = await self.tasks.cancel(identifier)
        if not job:
            raise NotFoundError()
        return {"job": job}

    async def artifacts(self, liked=False, limit=200, before=None, source="all", around=None):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValidationError("分页数量必须在 1 至 200 之间。")
        await self.clean_history()
        return await asyncio.to_thread(self.storage.artifact_page, liked, limit, before, source, around)

    async def roam_view(self, payload=None):
        if payload is not None:
            await self.tasks.database(self.storage.roam_view, payload)
        await self.clean_history()
        return await asyncio.to_thread(self.storage.roam_view)

    async def clear_generated(self, identifier, payload):
        if payload:
            raise ValidationError("清理图片请求不接受额外参数。")
        # Use the task storage boundary so cancellation drains the durable write.
        try:
            result = await self.tasks.database(self.storage.clear_generated, identifier)
        finally:
            # A disconnected request may still have committed its tombstones.
            self.events.publish("artifacts")
        stats = await self.cleanup.remove_pending()
        return dict(result, revision=await asyncio.to_thread(self.storage.artifact_revision),
                    pending_files=stats["pending"])

    async def feedback(self, identifier, payload):
        if "value" not in payload:
            raise ValidationError("缺少喜欢状态 value。")
        value = feedback_value(payload["value"])
        try:
            await self.tasks.database(self.storage.rate, identifier, value)
        except ValidationError:
            if not await asyncio.to_thread(self.storage.artifact, identifier):
                raise NotFoundError("图片已清理或不存在。") from None
            raise
        await self.clean_history()
        artifact = await asyncio.to_thread(self.storage.artifact, identifier)
        if not artifact:
            raise GoneError("图片已按历史清理规则移除。")
        await asyncio.to_thread(self._sync_recommendation)
        revision = await asyncio.to_thread(self.storage.artifact_revision)
        self.events.publish("feedback")
        return {"artifact": artifact, "artifact_revision": revision}

    async def history_settings(self, payload=None):
        if payload is not None:
            if "unliked_retention_days" not in payload:
                raise ValidationError("请填写历史图片保留天数。")
            document = await asyncio.to_thread(self.history.save, payload["unliked_retention_days"])
            cleanup = await self.clean_history(force=True)
            self.events.publish("settings")
        else:
            document = await asyncio.to_thread(self.history.get)
            cleanup = dict(self.cleanup.stats)
        counts = await asyncio.to_thread(self.storage.cleanup_counts)
        return dict(document, cleanup={**cleanup, **counts},
                    artifact_revision=await asyncio.to_thread(self.storage.artifact_revision))

    async def roam_settings(self, payload=None):
        async with self._roam_lock:
            if payload is None:
                document = await asyncio.to_thread(self.roam.get)
            else:
                if "prefetch_count" not in payload:
                    raise ValidationError("请填写漫游预取数量。")
                count = prefetch_count(payload["prefetch_count"])
                try:
                    previous = await asyncio.to_thread(self.roam.get)
                except ValidationError:
                    previous = self.roam.defaults()  # Saving can repair a damaged settings file.
                backend_id = selection(payload.get("backend_id", previous["backend_id"]), "生图后端")
                preset_id = selection(payload.get("preset_id", previous["preset_id"]), "候选预设")
                max_history = max_history_images(payload.get("max_history_images", previous["max_history_images"]))
                # Disabling must work even when a previously selected resource was deleted.
                if count:
                    if backend_id and not await asyncio.to_thread(self.storage.backend, backend_id):
                        raise ValidationError("漫游生图后端不存在，请重新选择。")
                    if preset_id and preset_id not in {item["id"] for item in (await asyncio.to_thread(self.candidates.list_presets))["presets"]}:
                        raise ValidationError("漫游候选预设不存在，请重新选择。")
                document = await asyncio.to_thread(self.roam.save, count, backend_id, preset_id, max_history)
                await self.clean_history(force=True, roam_only=True)
                self.events.publish("roam_settings")
            state = await asyncio.to_thread(self.storage.ensure_roam, document["epoch"], None, 0)
            return {key: document[key] for key in ("prefetch_count", "max_history_images", "backend_id", "preset_id")} | {
                "artifact_revision": await asyncio.to_thread(self.storage.artifact_revision),
                "paused": state["paused"], "preference_learning": await self._learning_available(),
                **({"error": state["error"]} if state.get("error") else {})}

    async def _roam_options(self, document):
        backends = await asyncio.to_thread(self.storage.backends)
        backend_id = document["backend_id"] or (backends[0]["id"] if backends else "")
        if not backend_id or not any(item["id"] == backend_id for item in backends):
            raise ValidationError("请在漫游设置中选择可用的生图后端。")
        presets = (await asyncio.to_thread(self.candidates.list_presets))["presets"]
        identifiers = [item["id"] for item in presets]
        preset_id = document["preset_id"] or (identifiers[0] if identifiers else "")
        if not preset_id or preset_id not in identifiers:
            raise ValidationError("请在漫游设置中选择可用的候选预设。")
        return backend_id, preset_id

    def _roam_candidate(self, context):
        # Candidate generation remains entirely owned by the candidate module.
        pool = self.candidates.provider.generate({"preset_id": context["preset_id"], "mode": "random_each_run"}, {"count": 4})
        if not pool:
            raise ValidationError("候选模块未提供合法提示词组合。")
        status = self._sync_recommendation()
        chosen, scored = pool[0], None
        if status.available and not self._recommendation_error:
            request_id = uuid.uuid4().hex
            request = ScoreRequest(request_id, "local", int(request_id[:16], 16), tuple(
                ScoreCandidate(item.id, item.positive, item.negative,
                               tuple(ScoreTerm(term.text, term.channel) for term in item.terms))
                for item in pool))
            try:
                scored = self.recommendation.score(request)
            except (RuntimeError, OSError):
                self._recommendation_error = "推荐评分暂不可用，本次沿用默认候选。"
            if scored is not None:
                values = {item.candidate_id: item.score for item in scored.scores}
                if (len(values) != len(pool) or len(scored.scores) != len(pool)
                        or set(values) != {item.id for item in pool}
                        or not all(type(value) in (int, float) and math.isfinite(value) for value in values.values())):
                    raise ValidationError("推荐服务必须为每个候选组合返回有效评分。")
                chosen = max(pool, key=lambda item: values[item.id])
        snapshot = {"candidate_id": chosen.id, "preset_id": context["preset_id"], "policy": type(self.recommendation).__name__,
                    "positive": chosen.positive, "negative": chosen.negative, "features": list(chosen.features),
                    "feature_version": status.feature_version, "policy_version": status.policy_version,
                    "state_revision": scored.state_revision if scored is not None else None,
                    "score": next((item.score for item in scored.scores if item.candidate_id == chosen.id), None) if scored else None,
                    "terms": [{"source_id": term.source_id, "id": term.id, "text": term.text,
                               "categories": list(term.categories), "channel": term.channel,
                               "content_revision": term.content_revision} for term in chosen.terms]}
        return chosen, snapshot

    async def ensure_roam(self, payload):
        anchor = payload.get("anchor_id")
        demand = payload.get("demand", False)
        if type(demand) is not bool:
            raise ValidationError("漫游 demand 须为布尔值。")
        if anchor is not None and (not isinstance(anchor, str) or not anchor or len(anchor) > 100):
            raise ValidationError("漫游 anchor_id 须为图片 ID 或 null。")
        async with self._roam_lock:
            document = await asyncio.to_thread(self.roam.get)
            count = document["prefetch_count"]
            enabled = bool(count) or demand
            target = (count + (anchor is None) if count else 1) if enabled else 0
            base = {"enabled": enabled, "prefetch_count": count, "target": target,
                    "preference_learning": await self._learning_available()}
            if enabled:
                await self.clean_history()
            state = await asyncio.to_thread(self.storage.ensure_roam, document["epoch"], anchor if enabled else None, target)
            if not enabled or state["paused"] or state["pending"] or state["ready"] >= target:
                return base | state
            try:
                backend_id, preset_id = await self._roam_options(document)
                base.update(backend_id=backend_id, preset_id=preset_id)
                context = {"kind": "roam", "anchor_id": anchor, "prefetch_count": count,
                           "backend_id": backend_id, "preset_id": preset_id, "epoch": document["epoch"]}
                chosen, snapshot = await asyncio.to_thread(self._roam_candidate, context)
                base["preference_learning"] = await self._learning_available()
                if self._recommendation_error:
                    base["recommendation_error"] = self._recommendation_error
                fields = generation_fields({"backend_id": backend_id, "request_id": "roam-" + uuid.uuid4().hex,
                                            "positive": chosen.positive, "negative": chosen.negative, "seed": -1})
                state = await asyncio.to_thread(self.storage.ensure_roam, document["epoch"], anchor, target, fields, snapshot)
            except NotFoundError:
                raise
            except Exception as exc:
                message = str(exc) if isinstance(exc, (ValueError, OSError)) else "漫游生成暂不可用，请在漫游设置中保存后重试。"
                await asyncio.to_thread(self.storage.pause_roam, document["epoch"], message)
                state = await asyncio.to_thread(self.storage.ensure_roam, document["epoch"], anchor, target)
            if state.get("job"):
                self.tasks.wake.set()
                self.events.publish("jobs")
            return base | state

    async def image(self, identifier):
        await self.clean_history()
        path = await self.tasks.cache_image(identifier)
        if path is None:
            raise NotFoundError()
        return path

    async def prompts(self, identifier):
        await self.clean_history()
        artifact = await asyncio.to_thread(self.storage.artifact, identifier)
        if not artifact:
            raise NotFoundError()
        return {"positive": artifact["positive"], "negative": artifact["negative"]}

    async def candidate(self, action, payload=None, identifier=None, query=None):
        data, query = payload or {}, query or {}
        if action == "tags":
            return await asyncio.to_thread(self.candidates.list_tags, query.get("query", ""),
                                          int(query.get("page", 1)), int(query.get("page_size", 15)))
        if action == "dataset":
            return await asyncio.to_thread(self.candidates.dataset_status)
        if action == "presets":
            return await asyncio.to_thread(self.candidates.list_presets)
        if action == "preset":
            return await asyncio.to_thread(self.candidates.load_preset, identifier)
        if action == "save_preset":
            result = await asyncio.to_thread(self.candidates.save_preset, data)
        elif action == "delete_preset":
            result = await asyncio.to_thread(self.candidates.delete_preset, identifier)
        elif action == "generate":
            return await asyncio.to_thread(self.candidates.generate, data)
        else:
            raise NotFoundError()
        self.events.publish("candidate")
        return result

    async def list_workflows(self):
        return {"workflows": await asyncio.to_thread(self.workflows.listing)}

    async def read_workflow(self, identifier):
        record = await asyncio.to_thread(self.workflows.read, identifier)
        if record is None:
            raise NotFoundError()
        return record

    async def save_workflow(self, document):
        result = await asyncio.to_thread(self.workflows.save_as, document)
        self.events.publish("workflows")
        return result

    async def delete_workflow(self, identifier, payload):
        result = await asyncio.to_thread(self.workflows.delete, identifier, payload.get("revision"),
                                         self.storage.detach_workflow)
        self.events.publish("workflows")
        self.events.publish("backends")
        return result
