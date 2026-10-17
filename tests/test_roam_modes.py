"""Two integration smokes for roam modes and prefetch invalidation; no GPU."""
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from aiohttp.test_utils import TestClient, TestServer
from backend.host import APPLICATION, create_app
from backend.store.candidate import SQLiteCandidateStore
from test_app import FakeBackend, configuration

class RoamModesSmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        static = self.root / "static"
        static.mkdir()
        self.static_patch = patch("backend.host.STATIC", static)
        self.static_patch.start()
        self.addCleanup(self.static_patch.stop)
        store = SQLiteCandidateStore(self.root / "candidate.sqlite3")
        with store.connect() as db:
            names = ["illustration", "garden", "sunlight", "night", "blue_sky"]
            db.executemany("INSERT INTO tags VALUES(?,?,?)", [(i+1, name, 100) for i, name in enumerate(names)])
            db.executemany("INSERT INTO correlations VALUES(?,?,?,?)", [(a,b,1,100) for a,b in itertools.combinations(range(1,6),2)])
            db.execute("INSERT INTO dataset VALUES(1,'neutral','smoke-v1',100,'ready')")
        await self.open_app()
        self.app.storage.save_backend(dict(configuration(), id="local"))
        self.app.candidates.save_preset(dict(id="neutral", name="Neutral", document=dict(
            base_positive=["illustration"], base_negative=["blurry"], min_tags=3, max_tags=3,
            pmi_threshold=0, min_cooccurrence=10, change_budget=2)))

    async def open_app(self):
        self.host = create_app(self.root, lambda config, session: FakeBackend())
        self.app = self.host[APPLICATION]
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()
        await self.app.tasks.stop()

    async def asyncTearDown(self):
        await self.client.close()

    async def put(self, payload):
        response = await self.client.put("/api/settings/roam", json=payload)
        data = await response.json()
        self.assertEqual(response.status, 200, data)
        return data

    async def ensure(self):
        response = await self.client.post("/api/roam/ensure", json={"anchor_id":None})
        data = await response.json()
        self.assertEqual(response.status, 200, data)
        return data

    async def rate(self, image, value):
        response = await self.client.put(f"/api/artifacts/{image['id']}/feedback", json={"value":value})
        self.assertEqual(response.status, 200, await response.text())

    def finish(self, job):
        self.app.storage.complete(job["id"], [{"node_id":"9","index":0,"filename":"neutral.png"}])
        return next(a for a in self.app.storage.artifacts(source="roam") if a["job_id"] == job["id"])

    async def test_switch_clears_old_prefetch_and_stay_retains_actual_prompt(self):
        await self.put(dict(prefetch_count=5, backend_id="local", preset_id="neutral"))
        first = (await self.ensure())["job"]
        current = self.finish(first)
        self.app.storage.roam_view(dict(artifact_id=current["id"], viewed_at=1))
        cached = self.finish((await self.ensure())["job"])
        await self.rate(cached, 1)
        queued = (await self.ensure())["job"]
        running = (await self.ensure())["job"]
        self.assertTrue(self.app.storage.claim_job(running["id"]))
        self.app.storage.attach_prompt(running["id"], "accepted-old-task")
        self.app.storage.update_job(running["id"], "running")
        saved = await self.put({"prompt_mode":"stay"})
        self.assertEqual(saved["prompt_mode"], "stay")
        self.assertEqual([a["id"] for a in self.app.storage.artifacts(source="roam")], [current["id"]])
        self.assertEqual(self.app.storage.job(queued["id"])["status"], "cancelled")
        self.app.storage.complete(running["id"], [{"node_id":"9","index":0,"filename":"late.png"}])
        self.assertEqual([a["id"] for a in self.app.storage.artifacts(source="roam")], [current["id"]])
        self.assertIn(cached["id"], [a["id"] for a in self.app.storage.artifacts(liked=True)])
        stay1 = (await self.ensure())["job"]
        stay2 = (await self.ensure())["job"]
        self.assertEqual((stay1["positive"],stay1["negative"]),(first["positive"],first["negative"]))
        self.assertEqual((stay2["positive"],stay2["negative"]),(first["positive"],first["negative"]))
        self.assertNotEqual(stay1["seed"], stay2["seed"])
        response = await self.client.put("/api/settings/roam", json={"prompt_mode":None})
        self.assertEqual(response.status,400)
        self.assertEqual((await (await self.client.get("/api/settings/roam")).json())["prompt_mode"],"stay")

    async def test_along_follows_selected_parent_instead_of_other_pool_candidates(self):
        from backend.contracts.recommendation import CandidateScore, RecommendationStatus, ScoreResult
        class LastScorer:
            def status(self): return RecommendationStatus(True,"smoke","smoke-features","smoke-policy")
            def score(self,request):
                return ScoreResult(tuple(CandidateScore(c.candidate_id,float(i)) for i,c in enumerate(request.candidates)),"smoke-features","smoke-policy",0)
        self.app.recommendation = LastScorer()
        self.app.recommendation_store = None
        await self.put(dict(prefetch_count=5,backend_id="local",preset_id="neutral"))
        initial = (await self.ensure())["job"]
        image = self.finish(initial)
        self.app.storage.roam_view(dict(artifact_id=image["id"],viewed_at=1))
        initial_snapshot = self.app.storage.roam_snapshot(initial["id"])
        calls = []
        original = self.app.candidates.provider.generate
        def record(context,constraints):
            pool = original(context,constraints)
            calls.append((constraints,pool))
            return pool
        self.app.candidates.provider.generate = record
        await self.put({"prompt_mode":"along"})
        first = (await self.ensure())["job"]
        second = (await self.ensure())["job"]
        first_snapshot = self.app.storage.roam_snapshot(first["id"])
        self.assertEqual(calls[0][0]["previous_candidate"]["candidate_id"],initial_snapshot["candidate_id"])
        self.assertEqual(first_snapshot["candidate_id"], calls[0][1][-1].id)
        self.assertEqual(calls[1][0]["previous_candidate"]["candidate_id"],first_snapshot["candidate_id"])
        for previous,current in [(initial,first),(first,second)]:
            self.assertLessEqual(len(set(previous["positive"].split(", ")) ^ set(current["positive"].split(", "))),2)
        reference = self.app.storage.roam_prompt_reference(self.app.roam.get()["epoch"],image["id"])
        self.assertEqual(reference["candidate_id"],self.app.storage.roam_snapshot(second["id"])["candidate_id"])
