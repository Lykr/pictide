"""One neutral HTTP smoke path from SQLite presets to queued generation."""
import itertools
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from backend.recommendation.contracts import CandidateScore, RecommendationStatus, ScoreResult
from backend.host import APPLICATION, create_app
from backend.store.candidate import SQLiteCandidateStore
from tests.backend.application.test_app import FakeBackend, configuration


class LastCombinationPolicy:
    def __init__(self): self.calls = []
    def status(self): return RecommendationStatus(True, "neutral", "neutral-features", "neutral-policy")
    def score(self, request):
        self.calls.append(request)
        return ScoreResult(tuple(CandidateScore(item.candidate_id,float(index)) for index,item in enumerate(request.candidates)), "neutral-features", "neutral-policy",0)


class CooccurrenceIntegrationSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_preset_preview_rounds_and_sqlite_roam(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = SQLiteCandidateStore(root / "libraries" / "neutral.sqlite3")
            with store.connect() as db:
                names = ["illustration", "garden", "sunlight", "standing", "smiling", "blue_sky"]
                db.executemany("INSERT INTO tags VALUES(?,?,?)", [(i+1,name,100) for i,name in enumerate(names)])
                db.executemany("INSERT INTO correlations VALUES(?,?,?,?)", [(a,b,1.0,100) for a,b in itertools.combinations(range(1,7),2)])
                db.execute("INSERT INTO dataset VALUES(1,'neutral smoke','smoke-v1',100,'ready',1)")
            backend = FakeBackend()
            backend.pending = True
            (root / "static").mkdir()
            with patch("backend.host.STATIC", root / "static"):
                app = create_app(root, lambda config, session: backend)
            async with TestClient(TestServer(app)) as client:
                response = await client.get("/api/candidate/tags?query=blue%20sky")
                self.assertEqual(response.status,200)
                tags_page = await response.json()
                self.assertEqual(tags_page["tags"][0]["name"],"blue_sky")
                self.assertEqual(tags_page["page_size"],15)
                response = await client.post("/api/candidate/relations",json={"anchor":"blue sky","terms":["garden","custom style"]})
                self.assertEqual(response.status,200,await response.text())
                relations = await response.json()
                self.assertEqual(relations["relations"][0]["count"],100)
                self.assertFalse(relations["relations"][1]["known"])
                self.assertEqual(len((await (await client.get("/api/jobs")).json())["jobs"]),0)
                document = {"base_positive":["illustration"],"base_negative":["blurry"],"min_tags":8,"max_tags":8,"pmi_threshold":.1,"min_cooccurrence":1,"change_budget":2}
                response = await client.post("/api/candidate/presets",json={"name":"中性测试","document":document})
                self.assertEqual(response.status,200,await response.text())
                preset = await response.json()
                options = {"preset_id":preset["id"],"mode":"sequence","seed":17,"sequence_step":0,"step_control":"increment"}
                response = await client.post("/api/candidate/generate",json=options)
                self.assertEqual(response.status,200,await response.text())
                preview = await response.json()
                self.assertEqual(preview["negative"],"blurry")
                self.assertEqual(preview["report"]["tag_count"],6)
                self.assertEqual(preview["report"]["stop_reason"],"no_eligible_tags")
                response = await client.put("/api/backends/local",json=configuration())
                self.assertEqual(response.status,200,await response.text())
                payload = {"backend_id":"local","request_id":"cooc-smoke-batch","candidate":options,"count":2,"repetitions":2,"seed":41}
                response = await client.post("/api/jobs",json=payload)
                self.assertEqual(response.status,202,await response.text())
                batch = await response.json()
                self.assertEqual(len(batch["jobs"]),4)
                self.assertEqual(batch["jobs"][0]["positive"],preview["positive"])
                self.assertEqual(batch["jobs"][0]["positive"],batch["jobs"][1]["positive"])
                self.assertEqual(batch["next_candidate"]["sequence_step"],2)
                self.assertLessEqual(batch["candidate_result"]["sequence"]["changes"],2)
                self.assertEqual((await (await client.post("/api/jobs",json=payload)).json())["job"]["id"],batch["job"]["id"])
                response = await client.put("/api/settings/roam",json={"prefetch_count":0,"max_history_images":10,"backend_id":"local","preset_id":preset["id"]})
                self.assertEqual(response.status,200,await response.text())
                self.assertEqual((await response.json())["preset_id"],preset["id"])
                self.assertFalse((root/"roam.json").exists())
                application = app[APPLICATION]
                await application.tasks.stop()
                for job in batch["jobs"]:
                    application.storage.update_job(job["id"], "completed")
                policy = LastCombinationPolicy()
                application.recommendation = policy
                application._recommendation_error = None
                application.recommendation_store = None
                response = await client.put("/api/settings/roam",json={"prefetch_count":1,"backend_id":"local","preset_id":preset["id"],"candidate_count":4})
                self.assertEqual(response.status,200,await response.text())
                self.assertEqual((await response.json())["candidate_count"],4)
                response = await client.post("/api/roam/ensure",json={"anchor_id":None})
                self.assertEqual(response.status,200,await response.text())
                roam = await response.json()
                self.assertFalse(roam["paused"])
                self.assertEqual(len(roam["job"]["positive"].split(", ")),6)
                self.assertEqual(len(policy.calls),1)
                self.assertEqual(len(policy.calls[0].candidates),4)
                for candidate in policy.calls[0].candidates:
                    self.assertTrue(all("_" not in term.text for term in candidate.terms))
                snapshot = application.storage.roam_snapshot(roam["job"]["id"])
                self.assertEqual(snapshot["candidate_id"],policy.calls[0].candidates[-1].candidate_id)
                self.assertTrue(snapshot["terms"])
                response = await client.delete("/api/candidate/presets/"+preset["id"],json={})
                self.assertTrue((await response.json())["deleted"])
