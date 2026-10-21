"""Two-job window smokes with isolated SQLite, event adapters and image files."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from backend.generation.base import BackendError
from backend.paths import DataPaths
from backend.store.sqlite import Repository
from backend.task.service import JobService
from tests.backend.application.test_app import FakeBackend, configuration


class Engine:
    def __init__(self):
        self.submitted = asyncio.Queue()
        self.pending = set()
        self.callbacks = {}
        self.requests = []
        self.removable = set()
        self.uncertain = set()
        self.reconciled = set()
        self.image_started = asyncio.Event()
        self.image_release = asyncio.Event()
        self.image_release.set()
        self.inspect_gates = {}

    def finish(self, request):
        self.pending.discard(request)
        if request in self.callbacks:
            self.callbacks[request]()


class EventBackend(FakeBackend):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.request = None
        self.connected = False

    @property
    def events_connected(self):
        return self.connected

    async def start_events(self, request_id, notify):
        self.request = request_id
        self.engine.callbacks[request_id] = notify
        self.connected = True
        return True

    async def stop_events(self):
        self.connected = False
        if self.request:
            self.engine.callbacks.pop(self.request, None)

    async def submit(self, plan, request_id):
        self.engine.requests.append(request_id)
        self.engine.pending.add(request_id)
        self.engine.submitted.put_nowait(request_id)
        if request_id in self.engine.uncertain:
            raise BackendError('Submission outcome unknown', uncertain=True)
        return 'external-' + request_id

    async def inspect(self, prompt_id):
        request = prompt_id.removeprefix('external-')
        gate = self.engine.inspect_gates.get(request)
        if gate:
            await gate.wait()
        if request in self.engine.pending:
            return {'state': 'running', 'outputs': []}
        return {'state': 'completed', 'outputs': [{'node_id': '9', 'index': 0,
                                                  'filename': request + '.png'}]}

    async def image(self, descriptor):
        self.engine.image_started.set()
        await self.engine.image_release.wait()
        return await super().image(descriptor)

    async def cancel(self, prompt_id):
        request = prompt_id.removeprefix('external-')
        if request not in self.engine.removable:
            return False
        self.engine.pending.discard(request)
        return True

    async def reconcile(self, request_id):
        return 'external-' + request_id if request_id in self.engine.reconciled else None


class TaskWindowSmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.paths = DataPaths(self.directory.name).ensure()
        self.repo = Repository(self.paths.database)
        self.repo.save_backend({**configuration(), 'id': 'local'})
        self.engine = Engine()
        self.worker = JobService(self.repo, None, lambda config, session: EventBackend(self.engine), self.paths)

    async def asyncTearDown(self):
        self.engine.image_release.set()
        for gate in self.engine.inspect_gates.values():
            gate.set()
        await self.worker.stop()
        self.directory.cleanup()

    def create(self, request, roam=False):
        job = self.repo.create_job(dict(backend_id='local', request_id=request,
                                       positive=request + ', sky', negative='text', seed=7))
        if roam:
            with self.repo.connection() as db:
                db.execute('INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES(?,?,?,?)',
                           (job['id'], 'smoke', '{}', job['created_at']))
        return job

    async def submitted(self, request):
        self.assertEqual(await asyncio.wait_for(self.engine.submitted.get(), 1), request)

    async def completed(self, job):
        async with asyncio.timeout(2):
            while self.repo.job(job['id'])['status'] != 'completed':
                await asyncio.sleep(.01)

    async def test_two_slots_refill_before_download_and_manual_priority(self):
        first, second = self.create('first'), self.create('second')
        await self.worker.start()
        await self.submitted('first')
        await self.submitted('second')
        roam = self.create('roam', roam=True)
        manual = self.create('manual')
        self.worker.wake.set()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.engine.submitted.get(), .1)
        self.engine.image_release.clear()
        self.engine.finish('second')  # results may arrive out of order
        await self.submitted('manual')
        await asyncio.wait_for(self.engine.image_started.wait(), 1)
        self.assertEqual(self.repo.job(second['id'])['status'], 'running')  # still saving
        self.assertEqual(self.repo.job(first['id'])['status'], 'running')
        self.assertEqual(self.repo.job(roam['id'])['status'], 'queued')
        self.assertEqual(self.engine.pending, {'first', 'manual'})
        self.engine.image_release.set()
        await self.completed(second)
        images = self.repo.artifacts()
        self.assertEqual([image['job_id'] for image in images], [second['id']])
        sidecar = next(self.paths.images.glob('*.json'))
        self.assertEqual(json.loads(sidecar.read_text()), {'positive': 'second, sky', 'negative': 'text'})
        self.assertEqual(self.engine.requests, ['first', 'second', 'manual'])

    async def test_cancel_running_holds_slot_and_restart_does_not_resubmit(self):
        first, second = self.create('first'), self.create('second')
        self.create('third')
        self.create('fourth')
        await self.worker.start()
        await self.submitted('first')
        await self.submitted('second')
        await self.worker.cancel(first['id'])
        self.worker.wake.set()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.engine.submitted.get(), .1)
        self.engine.removable.add('second')
        await self.worker.cancel(second['id'])
        await self.submitted('third')
        await self.worker.stop()
        await self.worker.start()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.engine.submitted.get(), .1)
        self.assertEqual(self.engine.requests, ['first', 'second', 'third'])
        self.engine.finish('first')
        self.worker.wake.set()  # restored accepted job uses polling, not event binding
        await self.submitted('fourth')
        self.assertEqual(self.repo.job(first['id'])['status'], 'cancelled')
        self.assertEqual(self.engine.pending, {'third', 'fourth'})
        self.assertEqual(self.repo.artifacts(), [])

    async def test_uncertain_submission_keeps_slot_and_can_reconcile_after_cancel(self):
        first = self.create('uncertain')
        self.create('second')
        self.create('third')
        self.engine.uncertain.add('uncertain')
        await self.worker.tick()
        self.assertEqual(self.engine.requests, ['uncertain', 'second'])
        self.assertEqual(self.repo.job(first['id'])['status'], 'unknown')
        await self.worker.tick()
        self.assertEqual(self.engine.requests, ['uncertain', 'second'])
        await self.worker.cancel(first['id'])
        self.engine.reconciled.add('uncertain')
        await self.worker.reconcile_unknown()
        self.assertEqual(self.repo.job(first['id'])['status'], 'cancelled')
        self.assertEqual(self.repo.job(first['id'])['backend_prompt_id'], 'external-uncertain')
        self.engine.finish('uncertain')
        await self.worker.tick()
        self.assertEqual(self.engine.requests, ['uncertain', 'second', 'third'])
        self.assertEqual(self.repo.artifacts(), [])

    async def test_slow_first_inspection_does_not_delay_second_slot_refill(self):
        self.create('first')
        second = self.create('second')
        await self.worker.tick()
        self.create('third')
        gate = self.engine.inspect_gates['first'] = asyncio.Event()
        self.engine.finish('second')
        check = asyncio.create_task(self.worker.tick())
        try:
            await self.submitted('first')
            await self.submitted('second')
            await self.submitted('third')
            self.assertFalse(check.done())
        finally:
            gate.set()
            await check
        await self.completed(second)

    async def test_restart_releases_two_missing_unknown_jobs_without_resubmitting(self):
        old = [self.create('old-first', roam=True), self.create('old-second', roam=True)]
        for job in old:
            self.repo.claim_job(job['id'])
            self.repo.update_job(job['id'], 'unknown', error='Connection lost during submission')
        self.create('new-first', roam=True)
        self.create('new-second', roam=True)
        await self.worker.start()
        await self.submitted('new-first')
        await self.submitted('new-second')
        await self.worker.stop()
        self.assertEqual(self.engine.requests, ['new-first', 'new-second'])
        self.assertEqual([self.repo.job(job['id'])['status'] for job in old], ['unknown', 'unknown'])
        self.assertEqual({job['request_id'] for job in self.repo.dispatch_jobs()}, {'new-first', 'new-second'})
        await self.worker.start()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.engine.submitted.get(), .1)
        self.assertEqual(self.engine.requests, ['new-first', 'new-second'])

    async def test_definitive_submission_failure_frees_slot_for_next_job(self):
        first = self.create('offline')
        self.create('second')
        third = self.create('third')
        submit = EventBackend.submit
        async def connect_failure(backend, job, request_id):
            if request_id == 'offline':
                raise BackendError('Connection refused', uncertain=False)
            return await submit(backend, job, request_id)
        with patch.object(EventBackend, 'submit', connect_failure):
            await self.worker.tick()
            await self.worker.tick()
        self.assertEqual(self.repo.job(first['id'])['status'], 'failed')
        self.assertEqual(self.repo.job(third['id'])['status'], 'running')
        self.assertEqual(self.engine.requests, ['second', 'third'])

    async def test_unknown_lookup_failure_holds_slot_then_absence_releases_for_late_recovery(self):
        first = self.create('uncertain')
        self.create('second')
        self.create('third')
        self.engine.uncertain.add('uncertain')
        await self.worker.tick()
        self.engine.pending.discard('uncertain')
        with patch.object(EventBackend, 'reconcile', AsyncMock(side_effect=BackendError('Backend offline'))):
            await self.worker.reconcile_unknown()
        await self.worker.tick()
        self.assertEqual(self.engine.requests, ['uncertain', 'second'])
        await self.worker.reconcile_unknown()
        await self.worker.tick()
        self.assertEqual(self.engine.requests, ['uncertain', 'second', 'third'])
        self.assertEqual(self.repo.job(first['id'])['status'], 'unknown')
        self.assertEqual(self.repo.artifacts(), [])
        self.engine.reconciled.add('uncertain')
        await self.worker.reconcile_unknown()
        await self.worker.tick()
        self.assertEqual(self.repo.job(first['id'])['status'], 'completed')
        self.assertEqual([a['job_id'] for a in self.repo.artifacts()], [first['id']])
        self.assertEqual(self.engine.requests, ['uncertain', 'second', 'third'])

    async def test_refill_failure_does_not_lose_already_finished_result(self):
        first = self.create('first')
        self.create('second')
        await self.worker.tick()
        self.engine.finish('first')
        fill = self.worker._fill_window
        calls = 0
        async def fail_after_release():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('Simulated refill failure')
            return await fill()
        with patch.object(self.worker, '_fill_window', fail_after_release):
            with self.assertRaises(RuntimeError):
                await self.worker.tick()
        self.assertEqual(self.repo.job(first['id'])['status'], 'completed')
        self.assertEqual(self.engine.requests, ['first', 'second'])
        self.assertEqual([a['job_id'] for a in self.repo.artifacts()], [first['id']])
