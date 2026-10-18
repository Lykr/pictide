"""One HTTP smoke for keyword preset persistence and filtered preview; no GPU."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from aiohttp.test_utils import TestClient, TestServer
from backend.host import APPLICATION, create_app

class BlockedKeywordsHttpSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_preset_roundtrip_preview_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            static = root / "static"; static.mkdir()
            with patch("backend.host.STATIC", static):
                app = create_app(root)
                store = app[APPLICATION].candidates.store
                with store.connect() as db:
                    db.executemany("INSERT INTO tags VALUES(?,?,?)",[(1,"blue_sky",100),(2,"soft_light",100),(3,"green_grass",100)])
                    db.executemany("INSERT INTO correlations VALUES(?,?,?,?)",[(1,2,1,100),(1,3,1,100),(2,3,1,100)])
                    db.execute("INSERT INTO dataset VALUES(1,'neutral','blocked-smoke',100,'ready',1)")
                document = dict(base_positive=["blue sky"],base_negative=["blurry"],min_tags=3,max_tags=3,
                                blocked_keywords=[" LIGHT ","sky","light"," ",""])
                async with TestClient(TestServer(app)) as client:
                    response = await client.post("/api/candidate/presets",json={"id":"blocked","name":"Blocked smoke","document":document})
                    self.assertEqual(response.status,200,await response.text())
                    saved = await response.json()
                    self.assertEqual(saved["document"]["blocked_keywords"],["light","sky"])
                    response = await client.post("/api/candidate/generate",json={"preset_id":"blocked","mode":"fixed_seed","seed":1})
                    self.assertEqual(response.status,200,await response.text())
                    result = await response.json()
                    self.assertEqual(result["positive"],"blue sky, green grass")
                    self.assertEqual(result["negative"],"blurry")
                    self.assertEqual(result["report"]["stop_reason"],"no_eligible_tags")
                    bad = dict(document,blocked_keywords=["sky",1])
                    response = await client.post("/api/candidate/presets",json={"id":"blocked","name":"Blocked smoke","document":bad})
                    self.assertEqual(response.status,400)
                async with TestClient(TestServer(create_app(root))) as client:
                    response = await client.get("/api/candidate/presets/blocked")
                    self.assertEqual((await response.json())["document"]["blocked_keywords"],["light","sky"])
                    self.assertEqual((await client.get("/api/jobs")).status,200)
