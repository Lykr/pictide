"""Manual batches remain atomic, recoverable and separate from roam images."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.domain import ConflictError, NotFoundError, ValidationError, generation_count
from backend.host import APPLICATION, create_app
from backend.store.sqlite import Repository
from tests.backend.application.test_app import FakeBackend, configuration


class GenerationBatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Repository(Path(self.temporary.name) / "pictide.sqlite3")
        self.repo.save_backend({**configuration(), "id": "local"})
        self.payload = {"request_id": "manual-batch-123", "backend_id": "local", "positive": "library",
                        "negative": "blurry", "seed": -1}

    def test_count_rejects_coercion_and_boundaries(self):
        for value in (0, 11, -1, True, "2", 1.5, None):
            with self.assertRaises(ValidationError):
                generation_count(value)
        self.assertEqual(generation_count(), 1)
        self.assertEqual(generation_count(10), 10)

    def test_random_batch_retries_survive_restart_backend_deletion_and_capacity(self):
        with patch("backend.domain.secrets.randbits", side_effect=(11, 22, 33)):
            jobs = self.repo.create_jobs(self.payload, 3)
        self.assertEqual([job["seed"] for job in jobs], [11, 22, 33])
        for n in range(7):
            self.repo.create_job({**self.payload, "request_id": f"other-{n:03d}"})
        self.repo.delete_backend("local")
        retried = Repository(self.repo.path).create_jobs(self.payload, 3)
        self.assertEqual([job["id"] for job in jobs], [job["id"] for job in retried])
        self.assertEqual([job["seed"] for job in retried], [11, 22, 33])
        with self.assertRaises(ConflictError):
            self.repo.create_jobs(self.payload, 2)
        with self.assertRaises(ConflictError):
            self.repo.create_jobs({**self.payload, "positive": "changed"}, 3)

    def test_fixed_seeds_wrap_and_keep_job_backend_snapshots(self):
        jobs = self.repo.create_jobs({**self.payload, "seed": 2**53-1}, 3)
        self.assertEqual([job["seed"] for job in jobs], [2**53-1, 0, 1])
        self.repo.save_backend({**configuration(), "id": "local", "name": "changed"})
        self.assertTrue(all(self.repo.job_backend(job["id"])["name"] == "Test backend" for job in jobs))
        self.assertTrue(all(job["source"] == "generate" for job in jobs))
        self.assertEqual(jobs[0]["request_id"], self.payload["request_id"])
        self.assertEqual(len({job["request_id"] for job in jobs}), 3)

    def test_single_job_legacy_retry_and_batch_conflict(self):
        old = self.repo.create_job(self.payload)
        retry = self.repo.create_jobs(self.payload)
        self.assertEqual(retry[0]["id"], old["id"])
        self.assertEqual(self.repo.create_job(self.payload)["id"], old["id"])
        with self.assertRaises(ConflictError):
            self.repo.create_jobs(self.payload, 2)
        self.assertEqual(len(self.repo.jobs()), 1)

    def test_capacity_failure_rolls_back_entire_batch(self):
        self.repo.create_jobs(self.payload, 8)
        with self.assertRaises(ValidationError):
            self.repo.create_jobs({**self.payload, "request_id": "no-room-123"}, 3)
        self.assertEqual(len(self.repo.jobs()), 8)
        with self.repo.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM generation_batches").fetchone()[0], 1)
        self.assertEqual(len(self.repo.create_jobs({**self.payload, "request_id": "no-room-123"}, 2)), 2)

    def test_concurrent_same_request_creates_one_batch(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.repo.create_jobs(self.payload, 3), range(4)))
        self.assertTrue(all([j["id"] for j in jobs] == [j["id"] for j in results[0]] for jobs in results))
        self.assertEqual(len(self.repo.jobs()), 3)

    def test_concurrent_capacity_never_partially_creates_batch(self):
        def reserve(n):
            try:
                return self.repo.create_jobs({**self.payload, "request_id": f"concurrent-{n}"}, 6)
            except ValidationError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(self.repo.jobs()), 6)

    def test_source_scoped_pagination_favorites_and_roam_buffer(self):
        manual = self.repo.create_jobs(self.payload, 2)
        for job in manual:
            self.repo.complete(job["id"], [{"node_id": "9", "index": n} for n in range(3)])
        state = self.repo.ensure_roam("epoch", None, 3, {**self.payload, "request_id": "roam-test-123"}, {"terms": []})
        self.assertEqual(state["ready"], 0)
        roam = state["job"]
        self.assertEqual(roam["source"], "roam")
        self.repo.complete(roam["id"], [{"node_id": "9", "index": n} for n in range(2)])
        page = self.repo.artifact_page(source="generate", limit=2)
        self.assertEqual(page["total"], 6)
        self.assertEqual(page["counts"], {"artifacts": 8, "generate": 6, "roam": 2, "liked": 0})
        identifiers = {item["id"] for item in page["artifacts"]}
        while page["has_more"]:
            page = self.repo.artifact_page(source="generate", limit=2, before=page["next_cursor"])
            self.assertFalse(identifiers.intersection(item["id"] for item in page["artifacts"]))
            identifiers.update(item["id"] for item in page["artifacts"])
        self.assertEqual(len(identifiers), 6)
        roam_images = self.repo.artifacts(source="roam")
        self.assertEqual(len(roam_images), 2)
        self.assertEqual(self.repo.ensure_roam("epoch", None, 3)["ready"], 2)
        self.assertEqual(self.repo.ensure_roam("epoch", roam_images[1]["id"], 3)["ready"], 1)
        with self.assertRaises(NotFoundError):
            self.repo.ensure_roam("epoch", next(iter(identifiers)), 3)
        with self.assertRaises(ValidationError):
            self.repo.artifact_page(source="roam", before=next(iter(identifiers)))
        with self.assertRaises(ValidationError):
            self.repo.artifact_page(source="unknown")
        self.repo.rate(next(iter(identifiers)), 1)
        self.repo.rate(roam_images[0]["id"], 1)
        self.assertEqual(self.repo.artifact_page(liked=True)["total"], 2)
        self.assertEqual(self.repo.artifact_page(liked=True, source="generate")["total"], 1)
        self.assertEqual(self.repo.artifact_page(liked=True, source="roam")["total"], 1)
        self.assertEqual(self.repo.artifact(roam_images[0]["id"])["source"], "roam")

    def test_batch_mapping_survives_cancellation_recovery_and_schema_upgrade(self):
        jobs = self.repo.create_jobs(self.payload, 2)
        self.repo.update_job(jobs[0]["id"], "cancelled")
        self.repo.update_job(jobs[1]["id"], "submitting")
        self.repo.recover_submissions()
        retry = Repository(self.repo.path).create_jobs(self.payload, 2)
        self.assertEqual([job["status"] for job in retry], ["cancelled", "unknown"])
        self.assertEqual(len(self.repo.jobs()), 2)
        with self.repo.connection() as db:
            db.execute("DROP TABLE generation_batches")
        migrated = Repository(self.repo.path)
        self.assertEqual(len(migrated.jobs()), 2)
        self.assertEqual(migrated.job(jobs[0]["id"])["status"], "cancelled")


class GenerationBatchAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fake = FakeBackend()
        self.host = create_app(self.temporary.name, lambda config, session: self.fake)
        self.app = self.host[APPLICATION]
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()
        await self.app.tasks.stop()
        await self.client.put("/api/backends/local", json=configuration())
        self.payload = {"request_id": "api-batch-request", "backend_id": "local", "positive": "library", "seed": 7, "count": 3}

    async def asyncTearDown(self):
        await self.client.close()
        self.temporary.cleanup()

    async def test_batch_retains_all_workflow_outputs_and_bootstrap_is_roam_only(self):
        response = await self.client.post("/api/jobs", json=self.payload)
        self.assertEqual(response.status, 202)
        batch = await response.json()
        self.assertEqual(batch["job"]["id"], batch["jobs"][0]["id"])
        self.assertEqual(len(batch["jobs"]), 3)
        for _ in range(3):
            await self.app.tasks.tick()
        self.assertEqual(len(self.fake.submissions), 3)
        generated = await (await self.client.get("/api/artifacts?source=generate")).json()
        self.assertEqual(generated["total"], 6)
        self.assertTrue(all(item["source"] == "generate" for item in generated["artifacts"]))
        bootstrap = await (await self.client.get("/api/bootstrap")).json()
        self.assertEqual(bootstrap["artifacts"], [])
        self.assertEqual(bootstrap["artifact_page"]["total"], 0)
        self.assertEqual(bootstrap["counts"]["generate"], 6)
        repeated = await (await self.client.post("/api/jobs", json=self.payload)).json()
        self.assertEqual([job["id"] for job in batch["jobs"]], [job["id"] for job in repeated["jobs"]])
        self.assertEqual((await self.client.post("/api/jobs", json={**self.payload, "count": 1})).status, 409)
        self.assertEqual((await self.client.get("/api/artifacts?source=wrong")).status, 400)
        self.assertEqual((await self.client.get("/api/artifacts?source=roam")).status, 200)

    async def test_invalid_count_queues_nothing_and_missing_count_is_single(self):
        for count in (0, 11, "2", True, None):
            response = await self.client.post("/api/jobs", json={**self.payload, "count": count})
            self.assertEqual(response.status, 400)
        self.assertEqual(self.app.storage.jobs(), [])
        response = await self.client.post("/api/jobs", json={key: value for key, value in self.payload.items() if key != "count"})
        self.assertEqual(response.status, 202)
        self.assertEqual(len((await response.json())["jobs"]), 1)
