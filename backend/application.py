"""Application use cases. HTTP handlers call this boundary, never feature storage."""
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import logging
import math
import hashlib
import json
import re
import uuid
import unicodedata

from . import __version__
from .contracts.recommendation import ScoreCandidate, ScoreRequest, ScoreTerm
from .candidate.rounds import validate_options
from .domain import GoneError, NotFoundError, ValidationError, feedback_value, generation_count, generation_fields, roam_can_enqueue
from .events import EventHub
from .generation import backend_capabilities
from .store.contracts import Storage
from .store.roam_settings import max_history_images, prefetch_count, selection, recommendation_options


def public_backend(config):
    result = {key: value for key, value in config.items() if key != "api_key"}
    result["has_api_key"] = bool(config.get("api_key"))
    result["capabilities"] = backend_capabilities(config)
    return result


def validate_generation_options(config, fields):
    capabilities = backend_capabilities(config)
    if capabilities["cloud"]:
        if fields.get("negative"):
            raise ValidationError("此生图接口不支持负向提示词，请清空负向提示词，或选择负向词为空的候选预设。")
        if fields.get("seed", -1) != -1:
            raise ValidationError("此生图接口不支持指定图像种子，请使用随机种子（-1）。")


class PictideApplication:
    @staticmethod
    def prepare_startup(paths, seed_dir):
        """Prepare vocabulary and model before composing application services."""
        if seed_dir is not None:
            from .store.portable_resources import initialize_resources
            initialize_resources(paths, seed_dir)
        from .recommand.resources import prepare_model
        prepare_model(paths.models / 'minilm')

    def __init__(self, paths, storage: Storage, tasks, candidates, recommendation,
                 history, cleanup, workflows, roam, recommendation_store=None, general=None):
        self.paths, self.storage, self.tasks = paths, storage, tasks
        self.candidates, self.recommendation = candidates, recommendation
        self.history, self.cleanup, self.workflows = history, cleanup, workflows
        self.recommendation_store = recommendation_store
        self._recommendation_error = None
        self._learning_wake = asyncio.Event()
        self._learning_task = None
        self._learning_stopping = False
        self._loop = None
        self.general = general
        self.roam = roam
        self._roam_lock = asyncio.Lock()
        self.events = EventHub()
        self.tasks.on_change = lambda: self.events.publish("jobs")

    async def start(self, session):
        self.tasks.session = self.tasks.connections.session = session
        self._loop = asyncio.get_running_loop()
        self._learning_stopping = False
        async with self._roam_lock:
            await self._refresh_roam_anchors()
        await self.cleanup.maybe_cleanup(force=True)
        await self.tasks.start()
        self._learning_task = asyncio.create_task(self._learn_feedback(), name="pictide-feedback-learning")
        self._request_learning()

    async def stop(self):
        self._learning_stopping = True
        self._learning_wake.set()
        await self.tasks.stop()
        if self._learning_task is not None:
            await self._learning_task
            self._learning_task = None
        self._loop = None

    def _request_learning(self):
        # Scoring runs in a thread. Marshal all wake-ups onto the application loop.
        if self._loop is not None and not self._learning_stopping:
            self._loop.call_soon_threadsafe(self._learning_wake.set)

    async def _learn_feedback(self):
        while True:
            await self._learning_wake.wait()
            self._learning_wake.clear()
            if self._learning_stopping:
                return
            try:
                await asyncio.to_thread(self._sync_recommendation)
            except Exception:
                logging.getLogger(__name__).exception("Background preference learning remains pending")
                self._recommendation_error = "推荐学习暂不可用，反馈已保存，将在下次操作重试。"
            try:
                await self.clean_history()
            except Exception:
                logging.getLogger(__name__).exception("Background feedback cleanup failed")

    async def clean_history(self, force=False, *, roam_only=False):
        before = self.cleanup.stats.get("revision", 0)
        result = await self.cleanup.maybe_cleanup(force=force, roam_only=roam_only)
        if self.cleanup.stats.get("revision", 0) != before:
            self.events.publish("artifacts")
        return result

    def _sync_recommendation(self):
        """Apply durable feedback in the single application learning worker."""
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
                "roam_view": view, "roam_settings": await self.roam_settings(),
                "artifact_revision": page["revision"], "counts": page["counts"],
                "artifact_page": {key: page[key] for key in ("has_more", "has_newer", "anchor_id", "next_cursor", "total", "revision")},
                "recommendation": asdict(recommendation) | {"error": self._recommendation_error or recommendation.error},
                "capabilities": {"generation": True, "feedback": True, "preference_learning": await self._learning_available(),
                                 "cooccurrence_prompts": True, "prompt_sequences": True, "events": True, "roam_prefetch": True}}

    async def preferences(self, page="1", all_terms=False):
        if not isinstance(page, str) or not re.fullmatch(r"[0-9]+", page):
            raise ValidationError("页码必须是正整数。")
        digits = page.lstrip("0")
        if not digits or len(digits) > 16 or int(digits) > 2**53 - 1:
            raise ValidationError("页码必须是 1 至 9007199254740991 的整数。")
        return asdict(await asyncio.to_thread(self.recommendation.preferences, "local", int(digits), all_terms=all_terms))

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
        if "api_key" not in draft and old and draft.get("kind", "comfyui") == old.get("kind", "comfyui"):
            draft["api_key"] = old.get("api_key", "")
        draft["id"] = identifier
        draft.pop("has_api_key", None)
        return draft

    async def save_backend(self, identifier, payload):
        previous_backend = await asyncio.to_thread(self.storage.backend, identifier)
        draft = await self.connection_draft(identifier, payload)
        draft = await self.tasks.connections.resolve_connection(draft)
        if draft.get("workflow_mode") == "custom" and any(
                key in payload for key in ("workflow_name", "workflow_id", "workflow_revision")):
            document = {key: draft[key] for key in ("workflow", "bindings", "output_nodes")}
            document["name"] = payload.get("workflow_name")
            document.update({key: payload[key] for key in ("workflow_id", "workflow_revision") if key in payload})
            saved = await asyncio.to_thread(self.workflows.save_and_apply, document, draft, self.storage.save_backend)
            self.events.publish("workflows")
        else:
            saved = await asyncio.to_thread(self.storage.save_backend, draft)
        self.events.publish("backends")
        async with self._roam_lock:
            roam = await asyncio.to_thread(self.roam.get)
            backends = await asyncio.to_thread(self.storage.backends)
            active_backend = roam["backend_id"] or (backends[0]["id"] if backends else "")
            if saved["id"] == active_backend:
                if (backend_capabilities(saved)["cloud"]
                        and (previous_backend is None or previous_backend.get("kind") != saved["kind"])):
                    roam = await asyncio.to_thread(self.roam.save, 0, roam["backend_id"],
                                                   roam["preset_id"], roam["max_history_images"])
                    self.events.publish("roam_settings")
                state = await asyncio.to_thread(self.storage.ensure_roam, roam["epoch"], None, 0)
                if state["paused"]:
                    # A new epoch isolates old failures, retaining all options and queued work.
                    await asyncio.to_thread(self.roam.save, roam["prefetch_count"], roam["backend_id"],
                                            roam["preset_id"], roam["max_history_images"])
                    # Publish last: the bounded event stream must retain the recovery signal.
                    self.events.publish("roam_settings")
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
            backend = await asyncio.to_thread(self.storage.backend, fields["backend_id"])
            if backend is None:
                raise ValidationError("生图后端不存在，请先保存后端配置。")
            validate_generation_options(backend, fields)
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
            validate_generation_options(validated, {**fields, **round_result})
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

    async def artifacts(self, liked=False, limit=200, before=None, source="all", around=None, tags=()):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValidationError("分页数量必须在 1 至 200 之间。")
        if tags and not liked:
            raise ValidationError("标签筛选仅用于喜欢图片。")
        await self.clean_history()
        return await asyncio.to_thread(self.storage.artifact_page, liked, limit, before, source, around, tuple(dict.fromkeys(tags)))

    async def preference_score(self, identifier):
        artifact = await asyncio.to_thread(self.storage.artifact, identifier)
        if artifact is None:
            raise NotFoundError()
        snapshot = await asyncio.to_thread(self.storage.roam_snapshot, artifact["job_id"])
        cached, error = await self._image_scores([{"artifact": artifact, "snapshot": snapshot}])
        row = cached["scores"].get(identifier)
        result = dict(status="missing_snapshot", score=None, love_score=None,
                      score_min=cached["score_min"], score_max=cached["score_max"],
                      state_revision=None, feature_version=None, reason="缺少完整生成快照，暂无法评分。")
        if row is None:
            return dict(result, status="unavailable", reason=error) if error else result
        value, minimum, maximum = row["score"], cached["score_min"], cached["score_max"]
        relative = 100 * ((value - minimum) / (maximum - minimum)) if minimum is not None and maximum is not None and maximum > minimum else None
        return dict(result, status="scored", score=value, love_score=relative,
                    state_revision=row["state_revision"], feature_version=row["feature_version"], reason=None)

    async def _image_scores(self, items, refresh=False):
        status = await asyncio.to_thread(self.recommendation.status)
        identifiers = [item["artifact"]["id"] for item in items]
        cached = await asyncio.to_thread(self.storage.image_score_cache, identifiers, status.feature_version, status.policy_version)
        unique, representative = {}, {}
        for item in items:
            identifier = item["artifact"]["id"]
            if not refresh and identifier in cached["scores"]:
                continue
            candidate = self._image_score_candidate(item["artifact"], item["snapshot"])
            if candidate is not None:
                key = (candidate.positive, candidate.negative, candidate.terms)
                canonical = unique.setdefault(key, candidate)
                representative[identifier] = canonical.candidate_id
        error = None
        if unique:
            reset = await asyncio.to_thread(self.recommendation_store.get_reset_state, "local")
            request = ScoreRequest(uuid.uuid4().hex, "local", 0, tuple(unique.values()), strategy="mean")
            try:
                scored = await asyncio.to_thread(self.recommendation.score, request)
                by_id = {row.candidate_id: row.mean_score for row in scored.scores}
                records = [dict(artifact_id=identifier, score=by_id[canonical], feature_version=scored.feature_version,
                                policy_version=scored.policy_version, state_revision=scored.state_revision)
                           for identifier, canonical in representative.items()]
                refreshed_at = datetime.now(timezone.utc).isoformat() if refresh else None
                await asyncio.to_thread(self.storage.save_image_scores, records, reset.revision, refreshed_at)
                cached = await asyncio.to_thread(self.storage.image_score_cache, identifiers, scored.feature_version, scored.policy_version)
            except (RuntimeError, OSError, ValueError):
                error = "评分更新失败，已保留现有缓存。" if cached["scores"] else "推荐服务暂不可用，请检查模型和学习状态。"
        return cached, error

    @staticmethod
    def _image_score_candidate(artifact, snapshot):
        if not isinstance(snapshot, dict):
            return None
        try:
            terms = tuple(ScoreTerm(term["text"], term.get("channel", "positive")) for term in snapshot["terms"])
            if not terms or any(not isinstance(t.text, str) or not t.text.strip().strip(",").strip()
                                or t.channel not in ("positive", "negative") for t in terms):
                return None
            for channel in ("positive", "negative"):
                actual = artifact[channel]
                joined = ", ".join(t.text.strip().strip(",").strip() for t in terms if t.channel == channel)
                if snapshot[channel] != actual or unicodedata.normalize("NFC", actual) != unicodedata.normalize("NFC", joined):
                    return None
            return ScoreCandidate(artifact["id"], artifact["positive"], artifact["negative"], terms)
        except (KeyError, TypeError, AttributeError):
            return None

    async def liked_ranked(self, tags=(), refresh=False):
        await self.clean_history()
        data = await asyncio.to_thread(self.storage.liked_scoring_inputs, tuple(dict.fromkeys(tags)))
        cached, error = await self._image_scores(data["items"], refresh)
        scores = cached["scores"]
        artifacts = [item["artifact"] for item in data["items"]]
        # Storage already orders equal scores by creation time and ID.
        artifacts.sort(key=lambda item: (item["id"] in scores, scores.get(item["id"], {}).get("score", 0)), reverse=True)
        return dict(artifacts=artifacts, revision=data["revision"],
                    state_revision=max((row["state_revision"] for row in scores.values()), default=None),
                    score_min=cached["score_min"], score_max=cached["score_max"],
                    scoring_available=error is None, error=error, refreshed_at=cached["refreshed_at"])

    async def liked_tags(self):
        return {"tags": await asyncio.to_thread(self.storage.liked_tags),
                "revision": await asyncio.to_thread(self.storage.artifact_revision)}

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
            raise ValidationError("缺少反馈状态 value。")
        value = feedback_value(payload["value"])
        try:
            artifact = await self.tasks.database(self.storage.rate, identifier, value)
        except ValidationError:
            if not await asyncio.to_thread(self.storage.artifact, identifier):
                raise NotFoundError("图片已清理或不存在。") from None
            raise
        if not artifact:
            raise NotFoundError("图片已清理或不存在。")
        revision = await asyncio.to_thread(self.storage.artifact_revision)
        self.events.publish("feedback")
        self._request_learning()
        return {"artifact": artifact, "artifact_revision": revision}

    async def general_settings(self, payload=None):
        if payload is None:
            return await asyncio.to_thread(self.general.get)
        document = await asyncio.to_thread(self.general.save, payload)
        self.events.publish("general_settings")
        return document

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

    async def _normalized_roam_anchors(self, document, pinned=None):
        presets = (await asyncio.to_thread(self.candidates.list_presets))["presets"]
        identifiers = [item["id"] for item in presets]
        preset_id = document["preset_id"] or (identifiers[0] if identifiers else "")
        # A deleted explicit preset remains invalid for generation, but must not prevent startup.
        if preset_id not in identifiers:
            preset_id = ""
        return await asyncio.to_thread(self.candidates.normalize_roam_anchors, preset_id,
                                       document["pinned_positive"] if pinned is None else pinned)

    async def _refresh_roam_anchors(self):
        document = await asyncio.to_thread(self.roam.get)
        anchors = await self._normalized_roam_anchors(document)
        updated = await asyncio.to_thread(self.roam.save_options, anchors=anchors)
        if document["epoch"] != updated["epoch"]:
            self.events.publish("roam_settings")
        return updated

    async def roam_settings(self, payload=None):
        recommendation = recommendation_options(payload or {})
        if payload is not None and "pinned_positive" in payload and (
                not isinstance(payload["pinned_positive"], list) or any(
                    not isinstance(text, str) or not text.strip() for text in payload["pinned_positive"])):
            raise ValidationError("pinned_positive 必须是完整且非空的提示词列表。")
        if payload is not None and "liked_tags_only" in payload and type(payload["liked_tags_only"]) is not bool:
            raise ValidationError("仅从喜欢图片抽取标签须为布尔值。")
        if payload is not None and "playback_interval_seconds" in payload:
            from .store.roam_settings import playback_interval_seconds
            playback_interval_seconds(payload["playback_interval_seconds"])
        if payload is not None and "prompt_mode" in payload:
            from .store.roam_settings import prompt_mode_value
            prompt_mode_value(payload["prompt_mode"])
        if payload is not None and "candidate_count" in payload:
            from .store.roam_settings import candidate_count_value
            candidate_count_value(payload["candidate_count"])
        async with self._roam_lock:
            if payload is None:
                document = await self._refresh_roam_anchors()
            elif payload and set(payload) <= {"playback_interval_seconds", "liked_tags_only", "prompt_mode", "candidate_count", "recommendation_strength", "strong_candidate_multiplier", "pinned_positive"}:
                previous = await asyncio.to_thread(self.roam.get)
                anchors = await self._normalized_roam_anchors(previous, payload.get("pinned_positive"))
                if ("pinned_positive" in payload and previous["prompt_mode"] == "stay"
                        and anchors["pinned_positive"] != previous["pinned_positive"]):
                    raise ValidationError("停泊时暂不可编辑画面锚点。")
                document = await asyncio.to_thread(self.roam.save_options, payload.get("liked_tags_only"),
                                                   payload.get("playback_interval_seconds"), payload.get("prompt_mode"), payload.get("candidate_count"), recommendation, anchors)
                self.events.publish("roam_settings")
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
                backends = await asyncio.to_thread(self.storage.backends)
                first_backend = backends[0]["id"] if backends else ""
                if (backend_id or first_backend) != (previous["backend_id"] or first_backend):
                    selected_backend = next((item for item in backends if item["id"] == (backend_id or first_backend)), None)
                    if selected_backend and backend_capabilities(selected_backend)["cloud"]:
                        count = 0
                # Disabling must work even when a previously selected resource was deleted.
                if count:
                    if backend_id and not await asyncio.to_thread(self.storage.backend, backend_id):
                        raise ValidationError("漫游生图后端不存在，请重新选择。")
                    if preset_id and preset_id not in {item["id"] for item in (await asyncio.to_thread(self.candidates.list_presets))["presets"]}:
                        raise ValidationError("漫游候选预设不存在，请重新选择。")
                anchors = await self._normalized_roam_anchors(previous | {"preset_id": preset_id}, payload.get("pinned_positive"))
                if ("pinned_positive" in payload and previous["prompt_mode"] == "stay"
                        and anchors["pinned_positive"] != previous["pinned_positive"]):
                    raise ValidationError("停泊时暂不可编辑画面锚点。")
                document = await asyncio.to_thread(self.roam.save, count, backend_id, preset_id, max_history,
                                                   payload.get("playback_interval_seconds"), payload.get("liked_tags_only"), payload.get("prompt_mode"), payload.get("candidate_count"), recommendation, anchors)
                if document["epoch"] != previous["epoch"]:
                    await self.clean_history(force=True, roam_only=True)
                self.events.publish("roam_settings")
            state = await asyncio.to_thread(self.storage.ensure_roam, document["epoch"], None, 0)
            return {key: document[key] for key in ("prefetch_count", "max_history_images", "backend_id", "preset_id", "playback_interval_seconds", "liked_tags_only", "prompt_mode", "candidate_count", "recommendation_strength", "strong_candidate_multiplier", "pinned_positive", "preset_base_positive")} | {
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
        mode = context.get("prompt_mode", "random")
        previous = self.storage.roam_prompt_reference(context["epoch"], context.get("anchor_id")) if mode != "random" else None
        strong = context.get("recommendation_strength", "standard") == "strong"
        strategy = "mean" if strong else "thompson"
        count = context.get("candidate_count", 10) * (context.get("strong_candidate_multiplier", 2) if strong else 1)
        constraints = {"count": count, "prompt_mode": mode, "previous_candidate": previous,
                       "pinned_positive": context.get("pinned_positive", [])}
        if context.get("liked_tags_only") and not (mode == "stay" and previous):
            prompts = self.storage.liked_positive_prompts()
            allowed = self.candidates.resolve_tag_pool(prompts)
            if not allowed:
                return None, None
            constraints["allowed_positive_tags"] = allowed
        pool = self.candidates.provider.generate({"preset_id": context["preset_id"], "mode": "random_each_run"}, constraints)
        if not pool:
            raise ValidationError("候选模块未提供合法提示词组合。")
        self._request_learning()
        status = self.recommendation.status()
        chosen, scored = pool[0], None
        score_reset_revision = self.recommendation_store.get_reset_state("local").revision if self.recommendation_store else 0
        if status.available and not self._recommendation_error and not (mode == "stay" and previous):
            request_id = uuid.uuid4().hex
            request = ScoreRequest(request_id, "local", int(request_id[:16], 16), tuple(
                ScoreCandidate(item.id, item.positive, item.negative,
                               tuple(ScoreTerm(term.text, term.channel) for term in item.terms))
                for item in pool), strategy=strategy)
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
                    "scoring_strategy": strategy if scored is not None else None,
                    "mean_score": next((item.mean_score for item in scored.scores if item.candidate_id == chosen.id), None) if scored else None,
                    "score_reset_revision": score_reset_revision,
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
            base = {"enabled": enabled, "prefetch_count": count, "target": target, "waiting_for_liked_tags": False,
                    "preference_learning": await self._learning_available()}
            if enabled:
                await self.clean_history()
            state = await asyncio.to_thread(self.storage.ensure_roam, document["epoch"], anchor if enabled else None, target)
            if not enabled or not roam_can_enqueue(state, target):
                return base | state
            try:
                backend_id, preset_id = await self._roam_options(document)
                base.update(backend_id=backend_id, preset_id=preset_id)
                context = {"kind": "roam", "anchor_id": anchor, "prefetch_count": count,
                           "backend_id": backend_id, "preset_id": preset_id, "epoch": document["epoch"],
                           "liked_tags_only": document["liked_tags_only"], "prompt_mode": document["prompt_mode"],
                           "candidate_count": document["candidate_count"],
                           "pinned_positive": document["pinned_positive"],
                           "recommendation_strength": document["recommendation_strength"],
                           "strong_candidate_multiplier": document["strong_candidate_multiplier"]}
                chosen, snapshot = await asyncio.to_thread(self._roam_candidate, context)
                if chosen is None:
                    return base | state | {"waiting_for_liked_tags": True}
                base["preference_learning"] = await self._learning_available()
                if self._recommendation_error:
                    base["recommendation_error"] = self._recommendation_error
                fields = generation_fields({"backend_id": backend_id, "request_id": "roam-" + uuid.uuid4().hex,
                                            "positive": chosen.positive, "negative": chosen.negative, "seed": -1})
                backend = await asyncio.to_thread(self.storage.backend, backend_id)
                validate_generation_options(backend, fields)
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

    async def candidate_library(self, action, payload=None, upload_path=None, filename=None):
        if action == "add":
            result = await asyncio.to_thread(self.candidates.add_library, upload_path, filename)
            self.events.publish("candidate")
            return result
        async with self._roam_lock:
            if action == "select":
                name = (payload or {}).get("filename")
                self.candidates = await asyncio.to_thread(self.candidates.select_library, name)
                await self._refresh_roam_anchors()
                self.events.publish("candidate")
                return {"selected": name}
            if action == "list":
                result = await asyncio.to_thread(self.candidates.list_libraries)
                selected = result["selected"]
                path = self.candidates.store.library_path
                current_name = "" if path.name.startswith(".") else path.name
                stamp = self.candidates.libraries.stamp(path)
                if selected != current_name or stamp != self.candidates.library_stamp:
                    self.candidates = await asyncio.to_thread(self.candidates.select_library, selected)
                    await self._refresh_roam_anchors()
                    self.events.publish("candidate")
                return result
        raise NotFoundError()

    async def candidate(self, action, payload=None, identifier=None, query=None):
        data, query = payload or {}, query or {}
        if action == "tags":
            return await asyncio.to_thread(self.candidates.list_tags, query.get("query", ""),
                                          int(query.get("page", 1)), int(query.get("page_size", 15)))
        if action == "relations":
            return await asyncio.to_thread(self.candidates.relations, data.get("anchor"), data.get("terms"))
        if action == "dataset":
            return await asyncio.to_thread(self.candidates.dataset_status)
        if action == "presets":
            return await asyncio.to_thread(self.candidates.list_presets)
        if action == "preset":
            return await asyncio.to_thread(self.candidates.load_preset, identifier)
        if action in ("save_preset", "delete_preset"):
            async with self._roam_lock:
                result = (await asyncio.to_thread(self.candidates.save_preset, data) if action == "save_preset"
                          else await asyncio.to_thread(self.candidates.delete_preset, identifier))
                await self._refresh_roam_anchors()
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
