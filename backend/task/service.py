"""Generation scheduling, recovery and result association, independent of HTTP."""
import asyncio
import logging
from pathlib import Path

from ..generation import create_backend
from ..generation.base import BackendError
from ..store.assets import local_image
from ..store.contracts import Storage
from .assets import cache_output
from .connections import BackendConnections

log = logging.getLogger(__name__)


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
        self._active_job = None
        self._active_backend = None
        self._event_owned = False
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
            await self._release_backend()

    async def _release_backend(self):
        backend = self._active_backend
        self._active_job = self._active_backend = None
        self._event_owned = False
        if backend is not None:
            await backend.stop_events()

    async def _backend_for_job(self, job):
        if job["id"] != self._active_job:
            await self._release_backend()
            config = await self.database(self.repository.job_backend, job["id"])
            self._active_backend = self.backend(config)
            self._active_job = job["id"]
            # Restored accepted jobs may have no event client binding; poll them.
            self._event_owned = job["status"] == "queued" and not job["backend_prompt_id"]
        backend = self._active_backend
        if self._event_owned and not backend.events_connected:
            await backend.start_events(job["request_id"], self.wake.set)
        return backend

    def _wait_timeout(self):
        if self._active_backend is None:
            return None
        if self._event_owned and self._active_backend.events_connected and not self._inspection_failed:
            return 30
        return 2

    async def reconcile_unknown(self):
        unknown = await self.database(self.repository.unknown_jobs)
        self._has_unknown = bool(unknown)
        for job in unknown:
            config = await self.database(self.repository.job_backend, job["id"])
            try:
                prompt_id = await self.backend(config).reconcile(job["request_id"])
                if prompt_id:
                    await self.database(self.repository.attach_prompt, job["id"], prompt_id)
                    await self.database(self.repository.update_job, job["id"], "running", error=None)
            except BackendError:
                # Unknown submissions must never be automatically submitted again.
                continue

    async def tick(self) -> bool:
        """Return true when this job releases the queue for immediate advancement."""
        self._inspection_failed = False
        job = await self.database(self.repository.next_job)
        if not job:
            await self._release_backend()
            return False
        backend = await self._backend_for_job(job)
        if not job["backend_prompt_id"]:
            if job["status"] != "queued":
                await self.database(self.repository.update_job,job["id"],"unknown",error="提交过程未确认完成，需要与后端核对；不会重复提交。")
                self._has_unknown = True
                return True
            if not await self.database(self.repository.claim_job,job["id"]):
                return False
            current = await self.database(self.repository.job, job["id"])
            if current["status"] == "cancelled":
                return True
            try:
                prompt_id = await backend.submit(job, job["request_id"])
            except BackendError as exc:
                await self.database(self.repository.update_job, job["id"], "unknown" if exc.uncertain else "failed", error=str(exc))
                self._has_unknown |= exc.uncertain
                return True
            except Exception:
                await self.database(self.repository.update_job,job["id"],"unknown",error="提交过程中发生内部异常，结果待核对；不会自动重新提交。")
                self._has_unknown = True
                return True
            job = await self.database(self.repository.attach_prompt, job["id"], prompt_id)
            if job["status"] == "cancelled":
                await backend.cancel(prompt_id)
                return True
            await self.database(self.repository.update_job, job["id"], "running", error=None)
        try:
            result = await backend.inspect(job["backend_prompt_id"])
        except BackendError as exc:
            # The job may still run: retry inspection, not submission.
            self._inspection_failed = True
            await self.database(self.repository.update_job, job["id"], error=str(exc))
            return False
        state = result["state"]
        if state == "completed":
            if not result.get("outputs"):
                await self.database(self.repository.update_job, job["id"], "failed", error="工作流已完成，但所选输出节点没有可展示的图片。")
            else:
                try:
                    outputs = [await cache_output(self.paths,backend,output,job) for output in result["outputs"]] if self.paths else result["outputs"]
                except (BackendError,OSError) as exc:
                    message = str(exc) if isinstance(exc,BackendError) else "无法写入 data/images，请检查磁盘空间和目录权限。"
                    await self.database(self.repository.update_job,job["id"],"failed",error=message)
                    return True
                await self.database(self.repository.complete, job["id"], outputs)
        elif state == "failed":
            await self.database(self.repository.update_job, job["id"], "failed", error=result.get("error") or "生图任务失败。")
        elif state == "unknown":
            self._has_unknown = True
            await self.database(self.repository.update_job, job["id"], "unknown", error="后端队列和历史中均没有该任务；不会自动重新提交。")
        else:
            await self.database(self.repository.update_job, job["id"], "running", error=None)
        return state in {"completed", "failed", "unknown"}

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
                await self.backend(config).cancel(job["backend_prompt_id"])
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
                await self._release_backend()
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
