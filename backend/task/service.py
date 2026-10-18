"""Generation scheduling, recovery and result association, independent of HTTP."""
import asyncio
import logging
from pathlib import Path
from dataclasses import dataclass

from ..generation import create_backend
from ..generation.base import BackendError, GenerationBackend
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
        self._pending_results = {}
        self._inspection_failed = False
        self._has_unknown = False

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
                log.warning("Job change notification failed")

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
            for iid in list(self._dispatches):
                await self._release_backend(iid)

    async def _release_backend(self, iid):
        dispatch = self._dispatches.pop(iid, None)
        if dispatch:
            await dispatch.backend.stop_events()

    async def _backend_for_job(self, job):
        dispatch = self._dispatches.get(job["id"])
        if dispatch is None:
            config = await self.database(self.repository.job_backend, job["id"])
            dispatch = _Dispatch(self.backend(config), job["status"] == "queued" and not job["backend_prompt_id"])
            self._dispatches[job["id"]] = dispatch
        if dispatch.event_owned and not dispatch.backend.events_connected:
            await dispatch.backend.start_events(job["request_id"], self.wake.set)
        return dispatch.backend

    def _wait_timeout(self):
        if not self._dispatches:
            return None
        if self._inspection_failed or any(not d.event_owned or not d.backend.events_connected or d.inspection_failed
                                          for d in self._dispatches.values()):
            return 2
        return 30

    async def reconcile_unknown(self):
        unknown = {job["id"]: job for job in await self.database(self.repository.unknown_jobs)}
        # A cancelled uncertain submission still occupies a slot and may acquire
        # its prompt id later. Keep its cancellation while reconciling identity.
        for job in await self.database(self.repository.dispatch_jobs):
            if job["backend_pending"] and not job["backend_prompt_id"]:
                unknown[job["id"]] = job
        self._has_unknown = bool(unknown)
        for job in unknown.values():
            config = await self.database(self.repository.job_backend, job["id"])
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
            try:
                prompt_id = await backend.submit(job, job["request_id"])
            except BackendError as exc:
                await self.database(self.repository.update_job, job["id"], "unknown" if exc.uncertain else "failed", error=str(exc))
                if exc.uncertain:
                    self._has_unknown = True
                else:
                    await self.database(self.repository.finish_dispatch, job["id"])
                    await self._release_backend(job["id"])
                    changed = True
                continue
            except Exception:
                await self.database(self.repository.update_job, job["id"], "unknown", error="提交过程中发生内部异常，结果待核对；不会自动重新提交。")
                self._has_unknown = True
                continue
            current = await self.database(self.repository.attach_prompt, job["id"], prompt_id)
            if current["status"] == "cancelled":
                try:
                    if await backend.cancel(prompt_id):
                        await self.database(self.repository.finish_dispatch, job["id"])
                        changed = True
                except BackendError:
                    pass
            else:
                await self.database(self.repository.update_job, job["id"], "running", error=None)
        return changed

    async def _inspect_job(self, job):
        backend = await self._backend_for_job(job)
        dispatch = self._dispatches[job["id"]]
        dispatch.inspection_failed = False
        try:
            result = await backend.inspect(job["backend_prompt_id"])
            return job, backend, result
        except BackendError as exc:
            dispatch.inspection_failed = True
            await self.database(self.repository.update_job, job["id"], error=str(exc))
        except Exception:
            dispatch.inspection_failed = True
            log.error("Job inspection encountered an internal error; generation was not resubmitted.")
        return job, backend, None

    async def _save_result(self, job, backend, result):
        current = await self.database(self.repository.job, job["id"])
        if current["status"] in {"cancelled", "completed", "failed"}:
            return
        if result["state"] == "failed":
            await self.database(self.repository.update_job, job["id"], "failed", error=result.get("error") or "生图任务失败。")
            return
        if not result.get("outputs"):
            await self.database(self.repository.update_job, job["id"], "failed", error="工作流已完成，但所选输出节点没有可展示的图片。")
            return
        try:
            outputs = [await cache_output(self.paths, backend, output, job) for output in result["outputs"]] if self.paths else result["outputs"]
            await self.database(self.repository.complete, job["id"], outputs)
        except (BackendError, OSError) as exc:
            message = str(exc) if isinstance(exc, BackendError) else "无法写入 data/images，请检查磁盘空间和目录权限。"
            await self.database(self.repository.update_job, job["id"], "failed", error=message)

    async def _flush_results(self):
        for iid, (job, backend, result) in list(self._pending_results.items()):
            try:
                await self._save_result(job, backend, result)
            except Exception:
                # Keep the captured result for a later attempt. Backend slots
                # and picture saves are separate; never generate this job again.
                self._inspection_failed = True
                log.error("Job result save encountered an internal error; result retained for retry.")
            else:
                self._pending_results.pop(iid, None)

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
                    await self.database(self.repository.update_job, job["id"], "unknown", error="后端队列和历史中均没有该任务；不会自动重新提交。")
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
        self.wake.set()
        return count

    async def cancel(self, iid):
        job = await self.database(self.repository.job, iid)
        if not job:
            return None
        if job["status"] in ("completed","failed","cancelled"):
            return job
        job = await self.database(self.repository.update_job, iid, "cancelled", error="已停止投喂。已运行的后端任务可能继续完成，不会中断其他任务。")
        if job["backend_prompt_id"]:
            config = await self.database(self.repository.job_backend, iid)
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
            except asyncio.CancelledError:
                raise
            except Exception:
                self._inspection_failed = True
                # Do not emit requests, workflow contents or authentication data.
                log.error("Job worker encountered an internal error; generation was not resubmitted.")
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
