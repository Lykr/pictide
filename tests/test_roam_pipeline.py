"""A prepared roam prompt overlaps the previous image, with bounded durable queues."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.candidate.contracts import Candidate, TagSnapshot
from backend.contracts.recommendation import CandidateScore, RecommendationStatus, ScoreResult
from backend.host import APPLICATION, create_app
from test_app import FakeBackend, configuration


class GatedBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.finish = asyncio.Event()

    async def inspect(self, prompt_id):
        self.started.set()
        await self.finish.wait()
        result = await super().inspect(prompt_id)
        result["outputs"] = result["outputs"][:1]
        return result


class PromptPool:
    def __init__(self, backend):
        self.backend = backend
        self.overlaps = []

    def generate(self, context, constraints):
        self.overlaps.append(self.backend.started.is_set() and not self.backend.finish.is_set())
        number = len(self.overlaps)
        return (Candidate(f"forest-{number}", f"forest, sunlight {number}", "",
                          terms=(TagSnapshot("smoke", "forest", "forest"),)),)


class Scorer:
    def __init__(self):
        self.requests = []

    def status(self):
        return RecommendationStatus(True, "smoke", "smoke-features", "smoke-policy")

    def score(self, request):
        self.requests.append(request)
        return ScoreResult(tuple(CandidateScore(c.candidate_id, 1.0) for c in request.candidates),
                           "smoke-features", "smoke-policy", 0)


class RoamPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        static = root / "static"
        static.mkdir()
        static_patch = patch("backend.host.STATIC", static)
        static_patch.start()
        self.addCleanup(static_patch.stop)
        self.backend = GatedBackend()
        self.host = create_app(root, lambda config, session: self.backend)
        self.app = self.host[APPLICATION]
        self.pool = PromptPool(self.backend)
        self.app.candidates = SimpleNamespace(provider=self.pool,
            list_presets=lambda: {"presets": [{"id": "neutral", "name": "Neutral"}]})
        self.scorer = Scorer()
        self.app.recommendation = self.scorer
        self.app.recommendation_store = None
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()
        await self.app.tasks.stop()  # Drive this same worker deterministically below.
        self.app.storage.save_backend({**configuration(), "id": "local"})
        self.app.roam.save(1, "local", "neutral")
        self.tick = None

    async def asyncTearDown(self):
        self.backend.finish.set()
        if self.tick:
            await self.tick
        await self.client.close()

    async def ensure(self):
        response = await self.client.post("/api/roam/ensure", json={"anchor_id": None})
        data = await response.json()
        self.assertEqual(response.status, 200, data)
        return data

    def manual(self, number):
        return self.app.storage.create_job({"request_id": f"manual-{number:04}", "backend_id": "local",
                                           "positive": "landscape", "negative": "", "seed": 1})

    async def test_prompt_and_score_are_ready_while_previous_image_is_generating(self):
        first = await self.ensure()
        self.assertEqual((first["target"], first["roam_pending"]), (2, 1))
        self.tick = asyncio.create_task(self.app.tasks.tick())
        await asyncio.wait_for(self.backend.started.wait(), 2)
        second = await self.ensure()
        self.assertEqual(second["roam_pending"], 2)
        self.assertEqual(self.pool.overlaps, [False, True])
        self.assertEqual(len(self.scorer.requests), 2)
        self.assertEqual(len(self.backend.submissions), 1)
        self.assertEqual(self.app.storage.job(first["job"]["id"])["status"], "running")
        self.assertEqual(second["job"]["status"], "queued")
        snapshot = self.app.storage.roam_snapshot(second["job"]["id"])
        self.assertEqual(snapshot["positive"], second["job"]["positive"])
        self.assertEqual(snapshot["score"], 1.0)
        repeated = await asyncio.gather(*(self.ensure() for _ in range(3)))
        self.assertTrue(all(r["roam_pending"] == 2 and "job" not in r for r in repeated))
        self.backend.finish.set()
        await self.tick
        state = await self.ensure()
        self.assertEqual((state["ready"], state["roam_pending"]), (1, 1))
        self.assertNotIn("job", state)  # Ready + prepared already meets target.
        await self.app.tasks.tick()
        state = await self.ensure()
        self.assertEqual((state["ready"], state["roam_pending"]), (2, 0))
        self.assertEqual(len(self.pool.overlaps), 2)

    async def test_manual_priority_capacity_wait_and_cancel_pause(self):
        manual = [self.manual(i) for i in range(9)]
        first = await self.ensure()
        self.assertEqual((first["pending"], first["roam_pending"]), (10, 1))
        full = await self.ensure()
        self.assertFalse(full["paused"])
        self.assertNotIn("job", full)
        self.assertEqual(len(self.pool.overlaps), 1)
        self.assertEqual(self.app.storage.next_job()["source"], "generate")
        self.app.storage.update_job(manual[0]["id"], "cancelled")
        second = await self.ensure()
        self.assertEqual((second["pending"], second["roam_pending"]), (10, 2))
        self.assertEqual(self.app.storage.next_job()["source"], "generate")
        self.app.roam.save(5, "local", "neutral")  # Old epoch jobs still occupy pipeline slots.
        old_epoch = await self.ensure()
        self.assertNotIn("job", old_epoch)
        self.assertEqual(old_epoch["roam_pending"], 2)
        self.assertFalse(old_epoch["paused"])
        self.app.storage.complete(first["job"]["id"], [{"node_id": "9", "index": 0, "filename": "first.png"}])
        third = await self.ensure()
        self.app.storage.update_job(third["job"]["id"], "cancelled")
        paused = await self.ensure()
        self.assertTrue(paused["paused"])
        self.assertNotIn("job", paused)

    async def test_store_transaction_bounds_concurrent_creators(self):
        repo = self.app.storage
        epoch = self.app.roam.get()["epoch"]
        def insert(i):
            return repo.ensure_roam(epoch, None, 20,
                {"request_id": f"concurrent-{i:04}", "backend_id": "local", "positive": "forest", "negative": "", "seed": 1},
                {"positive": "forest", "negative": "", "terms": []})
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(insert, range(4)))
        self.assertEqual(sum("job" in r for r in results), 2)
        self.assertEqual(repo.ensure_roam(epoch, None, 20)["roam_pending"], 2)
        self.assertEqual(len(repo.jobs()), 2)

    async def test_configured_candidate_pool_is_fully_scored_without_clearing_jobs(self):
        def generate(context, constraints):
            self.assertEqual(constraints["count"], 7)
            return tuple(Candidate(f"option-{i}", f"forest {i}", "",
                         terms=(TagSnapshot("smoke", f"forest-{i}", f"forest {i}"),))
                         for i in range(constraints["count"]))
        self.pool.generate = generate
        epoch = self.app.roam.get()["epoch"]
        response = await self.client.put("/api/settings/roam", json={"candidate_count": 7})
        self.assertEqual(response.status, 200)
        first = await self.ensure()
        self.assertEqual(len(self.scorer.requests[0].candidates), 7)
        self.assertEqual(first["job"]["positive"], "forest 0")
        response = await self.client.put("/api/settings/roam", json={"candidate_count": 3})
        self.assertEqual(response.status, 200)
        self.assertEqual(self.app.roam.get()["epoch"], epoch)
        self.assertEqual(self.app.storage.job(first["job"]["id"])["status"], "queued")

    async def test_strong_pool_and_strategy_switch_preserves_existing_tasks(self):
        counts = []
        def generate(context, constraints):
            counts.append(constraints["count"])
            return tuple(Candidate(f"option-{i}", f"forest {i}", "",
                         terms=(TagSnapshot("smoke", f"forest-{i}", f"forest {i}"),))
                         for i in range(constraints["count"]))
        self.pool.generate = generate
        def score(request):
            self.scorer.requests.append(request)
            return ScoreResult(tuple(CandidateScore(c.candidate_id, float(i))
                               for i, c in enumerate(request.candidates)), "smoke-features", "smoke-policy", 0)
        self.scorer.score = score
        epoch = self.app.roam.get()["epoch"]
        response = await self.client.put("/api/settings/roam", json={"recommendation_strength": "strong"})
        self.assertEqual(response.status, 200)
        first = await self.ensure()
        self.assertEqual((counts, self.scorer.requests[-1].strategy), ([8], "mean"))
        self.assertEqual(first["job"]["positive"], "forest 7")
        self.assertEqual(self.app.storage.roam_snapshot(first["job"]["id"])["scoring_strategy"], "mean")
        response = await self.client.put("/api/settings/roam", json={"recommendation_strength": "standard"})
        self.assertEqual(response.status, 200)
        second = await self.ensure()
        self.assertEqual((counts, self.scorer.requests[-1].strategy), ([8, 4], "thompson"))
        self.assertEqual(self.app.storage.job(first["job"]["id"])["status"], "queued")
        self.assertEqual(self.app.roam.get()["epoch"], epoch)
        self.assertEqual(second["roam_pending"], 2)

    async def test_candidate_provider_accepts_full_strong_pool(self):
        from backend.candidate.provider import CooccurrenceCandidateProvider
        provider = CooccurrenceCandidateProvider(SimpleNamespace(
            _prepare_generation=lambda *args: None,
            _generate_prepared=lambda *args: {"candidate_id": "sample", "positive": "forest",
                                              "negative": "", "selected_tags": []}))
        pool = provider.generate({"document": {}}, {"count": 100})
        self.assertEqual(len(pool), 100)
        with self.assertRaises(ValueError):
            provider.generate({"document": {}}, {"count": 101})
