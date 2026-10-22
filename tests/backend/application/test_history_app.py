from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer

from backend.host import create_app, APPLICATION
from backend.task.assets import cache_output
from backend.paths import DataPaths
from tests.backend.application.test_app import FakeBackend, configuration


class HistoryApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.paths = DataPaths(self.root).ensure()
        self.backend = FakeBackend()
        self.app = create_app(self.root,lambda config,session:self.backend)
        self.repo = self.app[APPLICATION].storage
        self.repo.save_backend(dict(configuration(),id="local"))
        self.client = TestClient(TestServer(self.app))

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def add_image(self, age, rating=None):
        payload = {"backend_id":"local","request_id":"history-"+str(len(self.repo.jobs())),"positive":"quiet garden","negative":"watermark","seed":1}
        job = self.repo.create_job(payload)
        output = await cache_output(self.paths,self.backend,{"node_id":"9","index":0,"filename":"sample.png","subfolder":"","type":"output"},job)
        self.repo.complete(job["id"],[output])
        artifact = next(row for row in self.repo.artifacts() if row["job_id"]==job["id"])
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET created_at=? WHERE id=?",((datetime.now(timezone.utc)-timedelta(days=age)).isoformat(),artifact["id"]))
        if rating is not None:
            self.repo.rate(artifact["id"],rating)
        return artifact,self.root/output["local_path"],payload

    async def test_startup_deletes_old_unrated_and_withdrawn_likes_but_preserves_likes_and_jobs(self):
        old,path,payload = await self.add_image(2)
        withdrawn,withdrawn_path,_ = await self.add_image(2,1)
        self.repo.rate(withdrawn["id"],None)
        liked,liked_path,_ = await self.add_image(2,1)
        recent,recent_path,_ = await self.add_image(0.5)
        await self.client.start_server()
        bootstrap = await (await self.client.get("/api/bootstrap")).json()
        self.assertEqual(bootstrap["counts"],{"artifacts":2,"liked":1,"roam":0,"generate":2})
        self.assertEqual(bootstrap["artifact_revision"],2)
        self.assertEqual((await (await self.client.get("/api/settings/history")).json())["unliked_retention_days"],1)
        self.assertFalse(path.exists())
        self.assertFalse(path.with_suffix(".json").exists())
        self.assertFalse(withdrawn_path.exists())
        self.assertTrue(liked_path.exists())
        self.assertTrue(recent_path.exists())
        self.assertEqual(len(bootstrap["jobs"]),4)
        self.assertEqual((await self.client.get(old["image_url"])).status,404)
        self.assertEqual((await self.client.get(f"/api/artifacts/{old['id']}/prompts")).status,404)
        self.assertEqual((await self.client.put(f"/api/artifacts/{old['id']}/feedback",json={"value":1})).status,404)
        retry = await self.client.post("/api/jobs",json=payload)
        self.assertEqual((await retry.json())["job"]["id"],old["job_id"])
        self.assertEqual(self.backend.submissions,[])
        with self.repo.connection() as db:
            self.assertIsNone(db.execute("SELECT value FROM feedback WHERE artifact_id=?",(withdrawn["id"],)).fetchone())

    async def test_list_operations_are_throttled_and_saved_policy_applies_immediately(self):
        await self.client.start_server()
        artifact,path,_ = await self.add_image(8)
        # The startup pass just ran: ordinary polling performs no new scan yet.
        self.assertEqual((await (await self.client.get("/api/artifacts")).json())["total"],1)
        self.app[APPLICATION].cleanup.last_attempt -= 61
        page = await (await self.client.get("/api/artifacts")).json()
        self.assertEqual(page["total"],0)
        self.assertEqual(page["revision"],1)
        self.assertFalse(path.exists())
        disabled = await self.client.put("/api/settings/history",json={"unliked_retention_days":0})
        self.assertEqual((await disabled.json())["unliked_retention_days"],0)
        kept,kept_path,_ = await self.add_image(20)
        self.app[APPLICATION].cleanup.last_attempt -= 61
        self.assertEqual((await (await self.client.get("/api/bootstrap")).json())["counts"]["artifacts"],1)
        self.assertTrue(kept_path.exists())
        enabled = await self.client.put("/api/settings/history",json={"unliked_retention_days":7})
        self.assertEqual((await enabled.json())["artifact_revision"],2)
        self.assertFalse(kept_path.exists())
        self.assertEqual(json.loads((self.root/"history-cleanup.json").read_text()),{"unliked_retention_days":7})

    async def test_like_is_applied_before_lazy_expiration(self):
        await self.client.start_server()
        artifact,path,_ = await self.add_image(8)
        self.app[APPLICATION].cleanup.last_attempt -= 61
        response = await self.client.put(f"/api/artifacts/{artifact['id']}/feedback",json={"value":1})
        self.assertEqual(response.status,200)
        self.assertEqual((await response.json())["artifact"]["feedback"],1)
        self.assertTrue(path.exists())
        self.assertEqual(self.repo.cleanup_counts()["deleted"],0)

    async def test_invalid_policy_fails_safe_and_can_be_repaired(self):
        artifact,path,_ = await self.add_image(8)
        (self.root/"history-cleanup.json").write_text('{"unliked_retention_days":true}')
        await self.client.start_server()
        self.assertTrue(path.exists())
        self.assertEqual((await self.client.get("/api/settings/history")).status,400)
        for invalid in [True,-1,1.5,3651,"7"]:
            self.assertEqual((await self.client.put("/api/settings/history",json={"unliked_retention_days":invalid})).status,400)
            self.assertTrue(path.exists())
        self.assertEqual((await self.client.put("/api/settings/history",json={"unliked_retention_days":7})).status,200)
        self.assertFalse(path.exists())

    async def test_late_image_cache_is_not_returned_or_resurrected(self):
        self.app[APPLICATION].history.save(0)
        artifact,path,_ = await self.add_image(8)
        path.unlink()
        path.with_suffix(".json").unlink()
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET local_path=NULL WHERE id=?",(artifact["id"],))
        original_image = self.backend.image
        async def delayed_image(output):
            self.repo.expire_artifacts(datetime.now(timezone.utc).isoformat())
            return await original_image(output)
        self.backend.image = delayed_image
        await self.client.start_server()
        self.assertEqual((await self.client.get(artifact["image_url"])).status,404)
        self.assertIsNone(self.repo.artifact(artifact["id"]))
        self.assertEqual(self.repo.cleanup_counts()["pending"],1)
        await self.client.put("/api/settings/history",json={"unliked_retention_days":0})
        self.assertFalse(path.exists())
        self.assertFalse(path.with_suffix(".json").exists())

    async def test_manual_score_cache_cleanup_preserves_data_and_rejects_late_scores(self):
        await self.client.start_server()
        removed, removed_path, _ = await self.add_image(0, -1)
        hidden, hidden_path, _ = await self.add_image(0, 1)
        kept, kept_path, _ = await self.add_image(0)
        records = [dict(artifact_id=item["id"], score=0.25, feature_version="fixture",
                        policy_version="fixture", state_revision=1) for item in (removed, hidden, kept)]
        self.repo.save_image_scores(records, 0)
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET deleted_at='2026-01-01' WHERE id=?", (removed["id"],))
            db.execute("UPDATE artifacts SET generated_hidden_at='2026-01-01',roam_hidden_at='2026-01-01' WHERE id=?", (hidden["id"],))

        def retained_data():
            with self.repo.connection() as db:
                tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                          "AND name NOT LIKE 'sqlite_%' AND name != 'artifact_preference_scores'")]
                return {name: [tuple(row) for row in db.execute('SELECT * FROM "'+name+'" ORDER BY rowid')]
                        for name in tables}

        original = retained_data()
        response = await self.client.post("/api/settings/cache/clear", json={})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"deleted_image_scores": 1})
        self.assertEqual(retained_data(), original)
        self.assertTrue(all(path.exists() for path in (removed_path, hidden_path, kept_path)))
        scores = self.repo.image_score_cache(tuple(item["id"] for item in (removed, hidden, kept)), "fixture", "fixture")
        self.assertEqual(set(scores["scores"]), {hidden["id"], kept["id"]})
        repeat = await self.client.post("/api/settings/cache/clear", json={})
        self.assertEqual(await repeat.json(), {"deleted_image_scores": 0})
        # Work started before deletion may finish after the cleanup transaction.
        late = [{**row, "score": 0.75} for row in records]
        self.repo.save_image_scores(late + [{**late[0], "artifact_id": "missing"}], 0)
        scores = self.repo.image_score_cache(tuple(row["artifact_id"] for row in late), "fixture", "fixture")["scores"]
        self.assertEqual(set(scores), {hidden["id"], kept["id"]})
        self.assertTrue(all(row["score"] == 0.75 for row in scores.values()))
        self.assertEqual((await self.client.get("/api/settings/cache/clear")).status, 405)
        self.assertEqual((await self.client.post("/api/settings/cache/clear", json={"all": True})).status, 400)
        self.assertEqual((await self.client.post("/api/settings/cache/clear", json={}, headers={"Origin": "https://example.invalid"})).status, 403)
