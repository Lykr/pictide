"""Generation scheduling, recovery and result association, independent of HTTP."""
import asyncio
import logging
from time import monotonic
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass

from ..generation import create_backend, backend_capabilities
from ..generation.base import BackendError, GenerationBackend, CompletedGeneration
from ..store.assets import local_image
from ..store.contracts import Storage
from .assets import cache_output
from .connections import BackendConnections

log = logging.getLogger(__name__)


@dataclass
class _Dispatch:
    backend: GenerationBackend
    event_owned: bool
    inspection_failed: bool = False


class JobService:
    def __init__(self, repository: Storage, session, backend_factory=create_backend, paths=None, on_change=None):
        self.repository = repository
        self.session = session
        self.backend_factory = backend_factory
        self.connections = BackendConnections(session, backend_factory)
        self.paths = paths
        self.on_change = on_change
        self.wake = asyncio.Event()
        self.task = None
        self._dispatches = {}
        self._submissions = {}
        self._pending_results = {}
        self._inspection_failed = False
        self._has_unknown = False
        self._started = {}
        self._log_jobs = {}
        self._result_log_errors = set()

    def _log_job(self, job, event, *, level=logging.INFO, reason=None, exc_info=None):
        """Log identity and timing only; the shared formatter redacts error echoes."""
        started = self._started.get(job["id"])
        elapsed = monotonic() - started if started is not None else 0.0
        if started is None and job.get("created_at"):
            created = datetime.fromisoformat(job["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - created).total_seconds()
        log.log(level, "Job %s: job_id=%s backend_id=%s backend_kind=%s elapsed=%.3fs%s",
                event, job["id"], job.get("backend_id", ""), job.get("backend_kind", "comfyui"),
                max(0.0, elapsed), f" reason={reason}" if reason else "", exc_info=exc_info,
                extra={"sensitive_values": tuple(job.get(key, "") for key in ("positive", "negative"))})
        if event in {"completed", "failed", "outcome unknown", "cancelled"}:
            self._started.pop(job["id"], None)

    def _log_sensitive_values(self):
        jobs = [*self._log_jobs.values(), *(item[0] for item in self._pending_results.values())]
        return tuple(job.get(key, "") for job in jobs for key in ("positive", "negative"))

    def backend(self, config):
        return self.backend_factory(config, self.session)

    async def cache_image(self, artifact_id: str) -> Path | None:
        """Return a local image, filling a legacy uncached result through its backend.

        Cache writes remain conditional on the artifact's active tombstone state.
        A cleanup race queues the copied files for deletion instead of reviving
        an expired image. Generation errors propagate to the application's API.
        """
        artifact = await self.database(self.repository.artifact, artifact_id)
        if not artifact or self.paths is None:
            return None
        cached = local_image(self.paths, artifact.get("local_path"))
        if cached:
            return cached
        source = await self.database(self.repository.artifact_source, artifact_id)
        if not source:
            return None
        backend = self.backend(source[0])
        job = await self.database(self.repository.job, artifact["job_id"])
        cached_output = await cache_output(self.paths, backend, source[1], job)
        retained = await self.database(self.repository.cache_artifact, artifact_id, cached_output)
        if not retained:
            return None
        return local_image(self.paths, cached_output["local_path"])

    async def database(self, operation, *args, **kwargs):
        # asyncio cancellation cannot stop a running SQLite thread. Drain it before
        # shutdown so commits finish and Windows does not retain open file handles.
        pending = asyncio.create_task(asyncio.to_thread(operation,*args,**kwargs))
        try:
            result = await asyncio.shield(pending)
        except asyncio.CancelledError:
            await pending
            self._notify_change(operation)
            raise
        self._notify_change(operation)
        return result

    def _notify_change(self, operation):
        if self.on_change and getattr(operation, "__name__", "") in {
                "update_job", "attach_prompt", "complete", "claim_job", "recover_submissions", "cancel_pending_jobs"}:
            try:
                self.on_change()
            except Exception:
                # Notifications must never turn a successful durable write into
                # a failed job operation or cause a generation resubmission.
                log.warning("Job change notification failed", exc_info=True,
                            extra={"sensitive_values": self._log_sensitive_values()})

    async def start(self):
        await self.database(self.repository.recover_submissions)
        self.task = asyncio.create_task(self.run(), name="pictide-jobs")

    async def stop(self):
        try:
            if self.task:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
        finally:
            submissions = list(self._submissions.values())
            for submission in submissions:
                submission.cancel()
            await asyncio.gather(*submissions, return_exceptions=True)
            for iid in list(self._dispatches):
                await self._release_backend(iid)

    async def _release_backend(self, iid):
        dispatch = self._dispatches.pop(iid, None)
        if dispatch:
            await dispatch.backend.stop_events()
        self._log_jobs.pop(iid, None)

    async def _backend_for_job(self, job):
        self._log_jobs[job["id"]] = job
        dispatch = self._dispatches.get(job["id"])
        if dispatch is None:
            config = await self.database(self.repository.job_backend, job["id"])
            dispatch = _Dispatch(self.backend(config), job["status"] == "queued" and not job["backend_prompt_id"])
            self._dispatches[job["id"]] = dispatch
        if dispatch.event_owned and not dispatch.backend.events_connected:
            await dispatch.backend.start_events(job["request_id"], self.wake.set)
        return dispatch.backend

    def _wait_timeout(self):
        dispatches = [dispatch for iid, dispatch in self._dispatches.items() if iid not in self._submissions]
        if not dispatches:
            return None
        if self._inspection_failed or any(not d.event_owned or not d.backend.events_connected or d.inspection_failed
                                          for d in dispatches):
            return 2
        return 30

    async def reconcile_unknown(self):
        unknown = {job["id"]: job for job in await self.database(self.repository.unknown_jobs)}
        pending = await self.database(self.repository.dispatch_jobs)
        pending_ids = {job["id"] for job in pending if job["backend_pending"]}
        # A cancelled uncertain submission still occupies a slot and may acquire
        # its prompt id later. Keep its cancellation while reconciling identity.
        for job in pending:
            if job["backend_pending"] and not job["backend_prompt_id"]:
                unknown[job["id"]] = job
        self._has_unknown = bool(unknown)
        for job in unknown.values():
            if job["id"] in self._submissions or job["id"] in self._pending_results:
                continue
            config = await self.database(self.repository.job_backend, job["id"])
            if not backend_capabilities(config)["recovery"]:
                # There is no remote handle to recover or retry a completed HTTP call.
                await self.database(self.repository.finish_dispatch, job["id"])
                await self._release_backend(job["id"])
                continue
            backend = self.backend(config)
            try:
                prompt_id = await backend.reconcile(job["request_id"])
                if prompt_id:
                    job = await self.database(self.repository.attach_prompt, job["id"], prompt_id)
                    if job["status"] == "cancelled":
                        if await backend.cancel(prompt_id):
                            await self.database(self.repository.finish_dispatch, job["id"])
                    else:
                        await self.database(self.repository.update_job, job["id"], "running", error=None)
                        self._log_job({**job, "backend_kind": config.get("kind", "comfyui")}, "accepted after recovery")
                elif job["id"] in pending_ids:
                    # Successful queue/history checks found no remote work. Keep
                    # the uncertain record for late recovery, without blocking
                    # unrelated jobs or ever resubmitting this operation.
                    await self.database(self.repository.finish_dispatch, job["id"])
                    await self._release_backend(job["id"])
                    self._log_job({**job, "backend_kind": config.get("kind", "comfyui")}, "unconfirmed backend slot released")
            except BackendError:
                # An uncertain submission is never automatically submitted again.
                continue

    async def _fill_window(self):
        changed = False
        for job in await self.database(self.repository.dispatch_jobs):
            if job["backend_pending"]:
                continue
            if not await self.database(self.repository.claim_job, job["id"]):
                changed = True
                continue
            current = await self.database(self.repository.job, job["id"])
            if current["status"] == "cancelled":
                await self.database(self.repository.finish_dispatch, job["id"])
                changed = True
                continue
            # Use the pre-claim queued snapshot to identify our new subscription.
            backend = await self._backend_for_job(job)
            if job.get("backend_kind", "comfyui") != "comfyui":
                # A cloud POST can take minutes; keep both slots and the worker responsive.
                submission = asyncio.create_task(self._submit_job(job, backend), name="pictide-cloud-" + job["id"])
                self._submissions[job["id"]] = submission
                submission.add_done_callback(lambda task, job=job: self._submission_done(job, task))
            else:
                changed = await self._submit_job(job, backend) or changed
        return changed

    def _submission_done(self, job, task):
        self._submissions.pop(job["id"], None)
        if not task.cancelled() and (exc := task.exception()) is not None:
            self._log_job(job, "cloud result processing error", level=logging.ERROR,
                          exc_info=(type(exc), exc, exc.__traceback__))
        self.wake.set()

    async def _submit_job(self, job, backend):
        self._started[job["id"]] = monotonic()
        self._log_job(job, "submitting")
        cloud = job.get("backend_kind", "comfyui") != "comfyui"
        try:
            submission = await backend.submit(job, job["request_id"])
        except BackendError as exc:
            current = await self.database(self.repository.update_job, job["id"], "unknown" if exc.uncertain else "failed", error=str(exc))
            event = "submission failed after cancellation" if current["status"] == "cancelled" else "outcome unknown" if exc.uncertain else "failed"
            self._log_job(job, event,
                          level=logging.ERROR, reason=str(exc), exc_info=True)
            if exc.uncertain:
                self._has_unknown = True
            if cloud or not exc.uncertain:
                await self.database(self.repository.finish_dispatch, job["id"])
                await self._release_backend(job["id"])
                return True
            return False
        except Exception:
            current = await self.database(self.repository.update_job, job["id"], "unknown", error="提交过程中发生内部异常，结果待核对；不会自动重新提交。")
            self._log_job(job, "submission error after cancellation" if current["status"] == "cancelled" else "outcome unknown",
                          level=logging.ERROR, exc_info=True)
            self._has_unknown = True
            if cloud:
                await self.database(self.repository.finish_dispatch, job["id"])
                await self._release_backend(job["id"])
            return cloud
        if isinstance(submission, CompletedGeneration):
            self._log_job(job, "accepted")
            # Capture bytes/URLs until durable saving succeeds, without inventing a remote ID.
            self._pending_results[job["id"]] = (job, backend, {"state": "completed", "outputs": submission.outputs})
            await self.database(self.repository.finish_dispatch, job["id"])
            await self._release_backend(job["id"])
            return True
        current = await self.database(self.repository.attach_prompt, job["id"], submission)
        self._log_job(job, "accepted")
        if current["status"] == "cancelled":
            try:
                if await backend.cancel(submission):
                    await self.database(self.repository.finish_dispatch, job["id"])
                    return True
            except BackendError:
                pass
        else:
            await self.database(self.repository.update_job, job["id"], "running", error=None)
        return False

    async def _inspect_job(self, job):
        backend = await self._backend_for_job(job)
        dispatch = self._dispatches[job["id"]]
        failed_before = dispatch.inspection_failed
        dispatch.inspection_failed = False
        try:
            result = await backend.inspect(job["backend_prompt_id"])
            return job, backend, result
        except BackendError as exc:
            dispatch.inspection_failed = True
            await self.database(self.repository.update_job, job["id"], error=str(exc))
            if not failed_before:
                self._log_job(job, "inspection failed", level=logging.ERROR, reason=str(exc), exc_info=True)
        except Exception:
            dispatch.inspection_failed = True
            if not failed_before:
                self._log_job(job, "inspection error", level=logging.ERROR, exc_info=True)
        return job, backend, None

    async def _save_result(self, job, backend, result):
        current = await self.database(self.repository.job, job["id"])
        if current["status"] in {"cancelled", "completed", "failed"}:
            return
        if result["state"] == "failed":
            reason = result.get("error") or "生图任务失败。"
            current = await self.database(self.repository.update_job, job["id"], "failed", error=reason)
            if current["status"] == "failed":
                self._log_job(job, "failed", level=logging.ERROR, reason=reason)
            return
        if not result.get("outputs"):
            current = await self.database(self.repository.update_job, job["id"], "failed", error="工作流已完成，但所选输出节点没有可展示的图片。")
            if current["status"] == "failed":
                self._log_job(job, "failed", level=logging.ERROR, reason="No displayable image outputs")
            return
        try:
            outputs = [await cache_output(self.paths, backend, output, job) for output in result["outputs"]] if self.paths else result["outputs"]
            await self.database(self.repository.complete, job["id"], outputs)
            # Cancellation may have won while caching the outputs.
            if (await self.database(self.repository.job, job["id"]))["status"] == "completed":
                self._log_job(job, "completed")
        except (BackendError, OSError) as exc:
            message = str(exc) if isinstance(exc, BackendError) else "无法写入 data/images，请检查磁盘空间和目录权限。"
            current = await self.database(self.repository.update_job, job["id"], "failed", error=message)
            self._log_job(job, "failed" if current["status"] == "failed" else "result save failed after cancellation",
                          level=logging.ERROR, reason=message, exc_info=True)

    async def _flush_results(self):
        for iid, (job, backend, result) in list(self._pending_results.items()):
            try:
                await self._save_result(job, backend, result)
            except Exception:
                # Keep the captured result for a later attempt. Backend slots
                # and picture saves are separate; never generate this job again.
                self._inspection_failed = True
                if iid not in self._result_log_errors:
                    self._result_log_errors.add(iid)
                    self._log_job(job, "result save error; result retained for retry", level=logging.ERROR, exc_info=True)
            else:
                self._pending_results.pop(iid, None)
                self._result_log_errors.discard(iid)

    async def tick(self) -> bool:
        """Maintain two backend slots; refill before caching finished outputs."""
        self._inspection_failed = False
        try:
            for iid in list(self._pending_results):
                await self.database(self.repository.finish_dispatch, iid)
                await self._release_backend(iid)
            advanced = await self._tick_window()
        except asyncio.CancelledError:
            # Saved prompt ids and running state allow startup recovery.
            raise
        except Exception:
            await self._flush_results()
            raise
        await self._flush_results()
        return advanced and not self._pending_results

    async def _tick_window(self):
        advanced = await self._fill_window()
        jobs = await self.database(self.repository.dispatch_jobs)
        pending_ids = {job["id"] for job in jobs if job["backend_pending"]}
        for iid in list(self._dispatches):
            if iid not in pending_ids:
                await self._release_backend(iid)
        checks = [asyncio.create_task(self._inspect_job(job)) for job in jobs
                  if job["backend_pending"] and job["backend_prompt_id"] and job["id"] not in self._pending_results]
        try:
            # Handle either slot as soon as its check finishes. A slow/failed
            # backend query must not delay refilling the other finished slot.
            for check in asyncio.as_completed(checks):
                job, backend, result = await check
                if result is None:
                    continue
                state = result["state"]
                if state in {"completed", "failed"}:
                    self._pending_results[job["id"]] = (job, backend, result)
                    await self.database(self.repository.finish_dispatch, job["id"])
                    await self._release_backend(job["id"])
                    await self._fill_window()
                    await self._flush_results()
                    advanced = True
                elif state == "unknown":
                    self._has_unknown = True
                    current = await self.database(self.repository.update_job, job["id"], "unknown", error="后端队列和历史中均没有该任务；不会自动重新提交。")
                    if job["status"] != "unknown" and current["status"] == "unknown":
                        self._log_job(job, "outcome unknown", level=logging.ERROR,
                                      reason="Backend queue and history have no matching task")
                else:
                    await self.database(self.repository.update_job, job["id"], "running", error=None)
        finally:
            for check in checks:
                if not check.done():
                    check.cancel()
            await asyncio.gather(*checks, return_exceptions=True)
        return advanced

    async def cancel_pending(self):
        count = await self.database(self.repository.cancel_pending_jobs)
        if count:
            log.info("Pending jobs cancelled: count=%s", count)
        self.wake.set()
        return count

    async def cancel(self, iid):
        job = await self.database(self.repository.job, iid)
        if not job:
            return None
        if job["status"] in ("completed","failed","cancelled"):
            return job
        job = await self.database(self.repository.update_job, iid, "cancelled", error="已停止投喂。已运行的后端任务可能继续完成，不会中断其他任务。")
        config = await self.database(self.repository.job_backend, iid)
        self._log_job({**job, "backend_kind": config.get("kind", "comfyui")}, "cancelled")
        if job["backend_prompt_id"]:
            try:
                if await self.backend(config).cancel(job["backend_prompt_id"]):
                    await self.database(self.repository.finish_dispatch, iid)
            except BackendError:
                pass
        self.wake.set()
        return job

    async def run(self):
        loop = asyncio.get_running_loop()
        reconcile_at = 0
        worker_failed = False
        while True:
            # Consume old signals before inspecting. Events arriving during submit
            # or inspect must remain set when the worker reaches its wait.
            self.wake.clear()
            advanced = False
            try:
                if loop.time() >= reconcile_at:
                    reconcile_at = loop.time() + 30
                    await self.reconcile_unknown()
                advanced = await self.tick()
                worker_failed = False
            except asyncio.CancelledError:
                raise
            except Exception:
                self._inspection_failed = True
                # Do not emit requests, workflow contents or authentication data.
                if not worker_failed:
                    log.error("Job worker encountered an internal error; generation was not resubmitted.",
                              exc_info=True, extra={"sensitive_values": self._log_sensitive_values()})
                worker_failed = True
            if advanced:
                continue
            timeout = self._wait_timeout()
            if self._has_unknown:
                until_reconcile = max(0, reconcile_at - loop.time())
                timeout = until_reconcile if timeout is None else min(timeout, until_reconcile)
            if self._inspection_failed and timeout is None:
                timeout = 2
            try:
                if timeout is None:
                    await self.wake.wait()
                else:
                    await asyncio.wait_for(self.wake.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
