"""Two HTTP smokes for liked-only roam and shared partial settings; no GPU."""
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from aiohttp.test_utils import TestClient, TestServer
from backend.host import APPLICATION, create_app
from backend.store.candidate import SQLiteCandidateStore
from tests.backend.application.test_app import FakeBackend, configuration

class LikedTagRoamSmoke(unittest.IsolatedAsyncioTestCase):
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
            db.execute("INSERT INTO dataset VALUES(1,'neutral','smoke-v1',100,'ready',1)")
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

    async def test_empty_pool_resumes_from_new_like_without_saving_settings(self):
        await self.put(dict(prefetch_count=1, backend_id="local", preset_id="neutral", liked_tags_only=True))
        empty = await self.ensure()
        self.assertTrue(empty["waiting_for_liked_tags"])
        self.assertFalse(empty["paused"])
        self.assertEqual(self.app.storage.jobs(), [])
        job = self.app.storage.create_job(dict(backend_id="local", request_id="manual-liked-fixture",
            positive="garden, sunlight, custom phrase", negative="night", seed=1))
        self.app.storage.complete(job["id"], [{"node_id":"9","index":0,"filename":"neutral.png"}])
        image = self.app.storage.artifacts(source="generate")[0]
        await self.rate(image, 1)
        generated = await self.ensure()
        self.assertFalse(generated["waiting_for_liked_tags"])
        self.assertFalse(generated["paused"])
        self.assertEqual(set(generated["job"]["positive"].split(", ")), {"illustration","garden","sunlight"})
        self.assertEqual(generated["job"]["negative"], "blurry")
        await self.rate(image, None)
        waiting = await self.ensure()
        self.assertTrue(waiting["waiting_for_liked_tags"])
        self.assertFalse(waiting["paused"])
        self.assertEqual(self.app.storage.job(generated["job"]["id"])["status"], "queued")
        await self.rate(image, 1)
        recovered = await self.ensure()
        self.assertIn("job", recovered)
        self.assertFalse(recovered["waiting_for_liked_tags"])

    async def test_partial_settings_preserve_other_fields_and_restart(self):
        await self.put(dict(prefetch_count=3, backend_id="local", preset_id="neutral", max_history_images=25, playback_interval_seconds=9))
        previous = self.app.roam.get()
        saved = await self.put({"liked_tags_only":True})
        self.assertTrue(saved["liked_tags_only"])
        after_flag = self.app.roam.get()
        for key in ("prefetch_count","backend_id","preset_id","max_history_images","playback_interval_seconds"):
            self.assertEqual(after_flag[key], previous[key])
        self.assertNotEqual(after_flag["epoch"], previous["epoch"])
        await self.put({"playback_interval_seconds":12})
        expected = dict(after_flag, playback_interval_seconds=12)
        self.assertEqual(self.app.roam.get(), expected)
        for payload in ({"liked_tags_only":None},{"liked_tags_only":1},{"liked_tags_only":"true"},
                        {"liked_tags_only":False,"playback_interval_seconds":None}):
            response = await self.client.put("/api/settings/roam", json=payload)
            self.assertEqual(response.status, 400)
            self.assertEqual(self.app.roam.get(), expected)
        bootstrap = await (await self.client.get("/api/bootstrap")).json()
        self.assertTrue(bootstrap["roam_settings"]["liked_tags_only"])
        await self.client.close()
        await self.open_app()
        restored = await (await self.client.get("/api/settings/roam")).json()
        self.assertTrue(restored["liked_tags_only"])
        self.assertEqual(restored["playback_interval_seconds"], 12)
        self.assertEqual(restored["prefetch_count"], 3)
