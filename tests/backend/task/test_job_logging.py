"""Task log correlation, exception traces and retry noise with simulated generation."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from backend.generation.base import BackendError
from backend.runtime_logging import RuntimeFormatter
from backend.store.sqlite import Repository
from backend.task.service import JobService
from tests.backend.application.test_app import FakeBackend, configuration


LOGGER = "backend.task.service"


class JobLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Repository(Path(directory.name) / "pictide.sqlite3")
        self.repo.save_backend({**configuration(), "id": "local"})
        self.backend = FakeBackend()
        self.worker = JobService(self.repo, None, lambda config, session: self.backend)
        self.addAsyncCleanup(self.worker.stop)
        self.job = self.repo.create_job(dict(backend_id="local", request_id="log-smoke",
            positive="private positive prompt", negative="private negative prompt", seed=1))

    async def test_submit_accept_and_complete_include_identity_and_monotonic_duration(self):
        with self.assertLogs(LOGGER, level="INFO") as captured:
            with patch("backend.task.service.monotonic", side_effect=[100, 100, 101, 105]):
                await self.worker.tick()
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(len(messages), 3)
        for message in messages:
            self.assertIn("job_id=" + self.job["id"], message)
            self.assertIn("backend_id=local backend_kind=comfyui", message)
            self.assertNotIn(self.job["positive"], message)
            self.assertNotIn(self.job["negative"], message)
        self.assertIn("Job submitting:", messages[0])
        self.assertIn("Job accepted:", messages[1])
        self.assertIn("Job completed:", messages[2])
        self.assertIn("elapsed=5.000s", messages[2])
        self.assertNotIn(self.job["id"], self.worker._started)
        self.assertEqual(self.repo.job(self.job["id"])["status"], "completed")

    async def test_uncertain_submission_preserves_trace_and_redaction_context(self):
        self.backend.submit = AsyncMock(side_effect=BackendError(
            "backend echoed " + self.job["positive"], uncertain=True))
        with self.assertLogs(LOGGER, level="INFO") as captured:
            await self.worker.tick()
        record = next(record for record in captured.records if "outcome unknown" in record.getMessage())
        self.assertEqual(record.levelname, "ERROR")
        self.assertIs(record.exc_info[0], BackendError)
        self.assertIsNotNone(record.exc_info[2])
        self.assertEqual(record.sensitive_values, (self.job["positive"], self.job["negative"]))
        rendered = RuntimeFormatter().format(record)
        self.assertIn("Traceback (most recent call last):", rendered)
        self.assertIn("BackendError: backend echoed [redacted]", rendered)
        self.assertNotIn(self.job["positive"], rendered)
        self.assertEqual(self.repo.job(self.job["id"])["status"], "unknown")
        self.backend.submit.assert_awaited_once()

    async def test_inspection_failures_log_once_until_recovery(self):
        self.backend.pending = True
        await self.worker.tick()
        self.backend.inspect = AsyncMock(side_effect=RuntimeError("inspection broke"))
        with self.assertLogs(LOGGER, level="ERROR") as captured:
            await self.worker.tick()
            await self.worker.tick()
        self.assertEqual(len(captured.records), 1)
        self.assertIs(captured.records[0].exc_info[0], RuntimeError)
        self.backend.inspect = AsyncMock(return_value={"state": "running", "outputs": []})
        await self.worker.tick()
        self.backend.inspect.side_effect = BackendError("offline")
        with self.assertLogs(LOGGER, level="ERROR") as captured:
            await self.worker.tick()
            await self.worker.tick()
        self.assertEqual(len(captured.records), 1)
        self.assertIs(captured.records[0].exc_info[0], BackendError)
        self.assertEqual(self.repo.job(self.job["id"])["status"], "running")

    async def test_result_save_retry_keeps_one_trace_and_then_logs_completion(self):
        original = self.repo.complete
        self.repo.complete = lambda *_: (_ for _ in ()).throw(RuntimeError("SQLite unavailable"))
        with self.assertLogs(LOGGER, level="INFO") as captured:
            await self.worker.tick()
            await self.worker.tick()
            self.repo.complete = original
            await self.worker.tick()
        failures = [record for record in captured.records if "result save error" in record.getMessage()]
        self.assertEqual(len(failures), 1)
        self.assertIs(failures[0].exc_info[0], RuntimeError)
        self.assertEqual(sum("Job completed:" in record.getMessage() for record in captured.records), 1)
        self.assertEqual(len(self.backend.submissions), 1)
        self.assertEqual(self.repo.job(self.job["id"])["status"], "completed")

    async def test_cancel_restored_job_uses_creation_time_and_cloud_callback_retains_trace(self):
        with self.repo.connection() as db:
            db.execute("UPDATE jobs SET created_at='2020-01-01T00:00:00+00:00' WHERE id=?", (self.job["id"],))
        with self.assertLogs(LOGGER, level="INFO") as captured:
            await self.worker.cancel(self.job["id"])
        message = captured.records[0].getMessage()
        self.assertIn("Job cancelled:", message)
        self.assertNotIn("elapsed=0.000s", message)
        self.assertIn("backend_kind=comfyui", message)
        async def fail():
            raise ValueError("response processing failed")
        task = asyncio.create_task(fail())
        await asyncio.gather(task, return_exceptions=True)
        with self.assertLogs(LOGGER, level="ERROR") as captured:
            self.worker._submission_done(self.job, task)
        record = captured.records[0]
        self.assertIs(record.exc_info[0], ValueError)
        self.assertIsNotNone(record.exc_info[2])
        self.assertEqual(record.sensitive_values, (self.job["positive"], self.job["negative"]))


if __name__ == "__main__":
    unittest.main()
