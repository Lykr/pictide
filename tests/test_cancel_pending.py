"""Queued-only bulk cancellation is atomic and never reaches a generation API."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import tempfile
import unittest
import uuid

from aiohttp.test_utils import TestClient, TestServer

from backend.host import create_app, APPLICATION
from backend.store.sqlite import Repository
from test_app import FakeBackend, configuration


def queued(repo, status="queued", roam=False, external=None):
    payload = {"backend_id": "test", "request_id": uuid.uuid4().hex,
               "positive": "library", "negative": "", "seed": 7}
    with repo.connection() as db:
        iid = repo._create_job(db, payload, capacity=1000)
        if roam:
            db.execute("INSERT INTO roam_jobs VALUES (?,?,?,?)", (iid, "epoch", "{}", "2026-10-16"))
    if external:
        repo.attach_prompt(iid, external)
    if status != "queued":
        repo.update_job(iid, status)
    return iid


class CancelPendingStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Repository(Path(self.directory.name) / "pictide.sqlite3")
        self.repo.save_backend(dict(configuration(), id="test"))

    def test_cancels_all_manual_queued_jobs_and_preserves_every_other_state(self):
        targets = [queued(self.repo), queued(self.repo)]
        retained = [queued(self.repo, status=status) for status in
                    ["submitting", "running", "unknown", "failed", "completed", "cancelled"]]
        retained += [queued(self.repo, roam=True), queued(self.repo, external="already-accepted")]
        before = {iid: self.repo.job(iid) for iid in retained}
        self.assertEqual(self.repo.cancel_pending_jobs(), 2)
        for iid in targets:
            self.assertEqual(self.repo.job(iid)["status"], "cancelled")
            self.assertFalse(self.repo.claim_job(iid))
        for iid in retained:
            self.assertEqual(self.repo.job(iid), before[iid])
        self.assertEqual(self.repo.cancel_pending_jobs(), 0)
        self.assertEqual(len(self.repo.jobs()), 10)

    def test_cancellation_is_not_limited_to_the_latest_jobs_or_page(self):
        targets = [queued(self.repo) for _ in range(105)]
        self.assertEqual(len(self.repo.jobs()), 100)
        self.assertEqual(self.repo.cancel_pending_jobs(), 105)
        self.assertTrue(all(self.repo.job(iid)["status"] == "cancelled" for iid in targets))

    def test_claim_and_cancel_race_cannot_cancel_an_already_claimed_job(self):
        for _ in range(16):
            iid = queued(self.repo)
            gate = Barrier(2)
            def claim():
                gate.wait(); return self.repo.claim_job(iid)
            def cancel():
                gate.wait(); return self.repo.cancel_pending_jobs()
            with ThreadPoolExecutor(max_workers=2) as pool:
                claim_future, cancel_future = pool.submit(claim), pool.submit(cancel)
                claimed, count = claim_future.result(), cancel_future.result()
            self.assertEqual((claimed, count, self.repo.job(iid)["status"]),
                             (True, 0, "submitting") if claimed else (False, 1, "cancelled"))
            if claimed:
                self.repo.update_job(iid, "completed")


class CancelPendingAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakeBackend()
        self.host = create_app(self.directory.name, lambda config, session: self.fake)
        self.app = self.host[APPLICATION]
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()
        await self.app.tasks.stop()
        self.app.storage.save_backend(dict(configuration(), id="test"))

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def test_api_preserves_roam_and_running_tasks_and_emits_existing_job_event(self):
        repo = self.app.storage
        targets = [queued(repo), queued(repo)]
        running = queued(repo, "running", external="external-running")
        roam = queued(repo, roam=True)
        notifications = []
        self.app.tasks.on_change = lambda: notifications.append("jobs")
        response = await self.client.post("/api/jobs/cancel-pending", json={})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"cancelled_count": 2})
        self.assertTrue(all(repo.job(iid)["status"] == "cancelled" for iid in targets))
        self.assertEqual(repo.job(running)["status"], "running")
        self.assertEqual(repo.job(roam)["status"], "queued")
        self.assertEqual(notifications, ["jobs"])
        self.assertEqual(self.fake.cancelled, [])
        self.assertEqual(self.fake.submissions, [])
        repeated = await self.client.post("/api/jobs/cancel-pending", json={})
        self.assertEqual(await repeated.json(), {"cancelled_count": 0})

    async def test_scope_cannot_be_expanded_and_cancelled_work_is_not_executed(self):
        iid = queued(self.app.storage)
        invalid = await self.client.post("/api/jobs/cancel-pending", json={"source": "all"})
        self.assertEqual(invalid.status, 400)
        self.assertEqual(self.app.storage.job(iid)["status"], "queued")
        self.assertEqual((await self.client.post("/api/jobs/cancel-pending", json={})).status, 200)
        await self.app.tasks.tick()
        self.assertEqual(self.fake.submissions, [])
        self.assertIsNotNone(self.app.storage.job(iid))
