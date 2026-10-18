"""Worker handoff smoke tests using isolated SQLite and a simulated backend."""
import asyncio
from pathlib import Path
import tempfile
import time
import unittest

from backend.store.sqlite import Repository
from backend.task.service import JobService
from test_app import FakeBackend, configuration


class RecordingRepository(Repository):
    def __init__(self, path):
        super().__init__(path)
        self.completed_at = {}

    def complete(self, iid, outputs):
        result = super().complete(iid, outputs)
        self.completed_at[iid] = time.perf_counter()
        return result


class RecordingBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.submitted = asyncio.Queue()
        self.inspected = asyncio.Queue()
        self.submitted_at = {}
        self.pending_requests = set()

    async def submit(self, plan, request_id):
        prompt_id = await super().submit(plan, request_id)
        self.submitted_at[request_id] = time.perf_counter()
        self.submitted.put_nowait(request_id)
        return prompt_id

    async def inspect(self, prompt_id):
        self.inspected.put_nowait(prompt_id)
        if prompt_id.removeprefix('external-') in self.pending_requests:
            return {'state': 'running', 'outputs': []}
        return await super().inspect(prompt_id)


class WorkerHandoffSmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = RecordingRepository(Path(self.directory.name) / 'pictide.sqlite3')
        self.repo.save_backend({**configuration(), 'id': 'local'})
        self.backend = RecordingBackend()
        self.worker = JobService(self.repo, None, lambda config, session: self.backend)
        self.addAsyncCleanup(self.worker.stop)

    def create(self, request_id, roam=False):
        job = self.repo.create_job(dict(backend_id='local', request_id=request_id,
                                       positive='landscape', negative='', seed=1))
        if roam:
            with self.repo.connection() as db:
                db.execute('INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES(?,?,?,?)',
                           (job['id'], 'smoke', '{}', job['created_at']))
        return job

    async def test_completed_job_hands_off_immediately_with_manual_priority(self):
        first = self.create('accepted-roam', roam=True)
        self.repo.attach_prompt(first['id'], 'external-accepted-roam')
        self.repo.update_job(first['id'], 'running')
        self.create('queued-roam', roam=True)
        self.create('queued-manual')
        self.backend.pending_requests.add('queued-roam')
        await self.worker.start()
        self.assertEqual(await asyncio.wait_for(self.backend.submitted.get(), 1), 'queued-manual')
        self.assertLess(self.backend.submitted_at['queued-manual'] - self.repo.completed_at[first['id']], 0.8)
        self.assertEqual(await asyncio.wait_for(self.backend.submitted.get(), 1), 'queued-roam')
        self.assertEqual([request for _, request in self.backend.submissions], ['queued-manual', 'queued-roam'])

    async def test_running_job_waits_and_wakes_without_submitting_again(self):
        first = self.create('running-first')
        second = self.create('queued-second')
        self.backend.pending_requests.add('running-first')
        await self.worker.start()
        await asyncio.wait_for(self.backend.inspected.get(), 1)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.backend.inspected.get(), 0.1)
        self.worker.wake.set()
        await asyncio.wait_for(self.backend.inspected.get(), 1)
        self.assertEqual(len(self.backend.submissions), 1)
        self.assertEqual(self.repo.job(first['id'])['status'], 'running')
        self.assertEqual(self.repo.job(second['id'])['status'], 'queued')

    async def test_empty_queue_waits_then_new_work_wakes_it(self):
        checks = asyncio.Queue()
        original = self.repo.next_job
        loop = asyncio.get_running_loop()
        def next_job():
            loop.call_soon_threadsafe(checks.put_nowait, None)
            return original()
        self.repo.next_job = next_job
        await self.worker.start()
        await asyncio.wait_for(checks.get(), 1)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(checks.get(), 0.1)
        self.create('new-work')
        self.backend.pending_requests.add('new-work')
        self.worker.wake.set()
        self.assertEqual(await asyncio.wait_for(self.backend.submitted.get(), 1), 'new-work')