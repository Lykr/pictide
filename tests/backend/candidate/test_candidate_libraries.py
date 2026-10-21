"""Small end-to-end smokes for selectable local vocabularies."""
from contextlib import closing
import gzip
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from backend.store.candidate import SQLiteCandidateStore


def vocabulary(path, first="blue_sky", second="garden", minimum=10):
    store = SQLiteCandidateStore(path)
    with store.connect() as db:
        db.executemany("INSERT INTO tags VALUES(?,?,5000)", [(1, first), (2, second)])
        db.execute("INSERT INTO correlations VALUES(1,2,0.6780719051126377,4000)")
        db.execute("INSERT INTO dataset VALUES(1,'neutral library smoke','v1',10000,'ready',?)", (minimum,))
        db.execute("INSERT INTO presets VALUES('foreign','foreign','{}')")
    return path


class LibrarySmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.data = self.root / "data"
        self.static = self.root / "static"
        self.static.mkdir()
        (self.static / "index.html").write_text("test", encoding="utf-8")
        self.first = vocabulary(self.root / "first.sqlite3")
        self.second = vocabulary(self.root / "second.sqlite3", "red_sky", "forest")
        self.client = await self.open_client()

    async def open_client(self):
        with patch("backend.host.STATIC", self.static):
            app = create_app(self.data)
        client = TestClient(TestServer(app))
        await client.start_server()
        return client

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def upload(self, payload, filename):
        form = FormData()
        form.add_field("file", payload, filename=filename, content_type="application/octet-stream")
        return await self.client.post("/api/candidate/library", data=form)

    async def select(self, filename):
        response = await self.client.put("/api/candidate/library", json={"filename": filename})
        self.assertEqual(response.status, 200, await response.text())

    async def test_upload_copy_select_and_restart_keep_personal_preset(self):
        self.assertEqual((await (await self.client.get("/api/candidate/library")).json())["libraries"], [])
        response = await self.upload(self.first.read_bytes(), "vocabulary.sqlite3")
        self.assertEqual(response.status, 201, await response.text())
        first = await response.json()
        self.assertEqual((first["tag_count"], first["relation_count"]), (2, 1))
        with closing(sqlite3.connect(self.data / "libraries" / first["filename"])) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='presets'").fetchone()[0], 0)
        await self.select(first["filename"])
        tags = await (await self.client.get("/api/candidate/tags")).json()
        self.assertEqual({x["name"] for x in tags["tags"]}, {"blue_sky", "garden"})
        document = dict(base_positive=["custom anchor"], base_negative=[], blocked_keywords=[], min_tags=3, max_tags=3,
                        pmi_threshold=0, min_cooccurrence=10, change_budget=2)
        response = await self.client.post("/api/candidate/presets", json={"name": "personal", "document": document})
        self.assertEqual(response.status, 200, await response.text())
        preset = await response.json()
        response = await self.upload(gzip.compress(self.second.read_bytes()), "vocabulary.sqlite3.gz")
        self.assertEqual(response.status, 201, await response.text())
        second = await response.json()
        self.assertEqual(second["filename"], "vocabulary-2.sqlite3")
        await self.select(second["filename"])
        response = await self.client.post("/api/candidate/generate", json={"preset_id": preset["id"], "mode": "fixed_seed", "seed": 7})
        self.assertEqual(response.status, 200, await response.text())
        prompt = (await response.json())["positive"]
        self.assertIn("red sky", prompt)
        self.assertNotIn("blue sky", prompt)
        self.assertIn("custom anchor", prompt)
        shutil.copy2(self.first, self.data / "libraries" / "manual.sqlite3")
        listing = await (await self.client.get("/api/candidate/library")).json()
        self.assertIn("manual.sqlite3", {x["filename"] for x in listing["libraries"]})
        await self.select("manual.sqlite3")
        await self.client.close()
        self.client = await self.open_client()
        listing = await (await self.client.get("/api/candidate/library")).json()
        self.assertEqual(listing["selected"], "manual.sqlite3")
        saved = await (await self.client.get("/api/candidate/presets/" + preset["id"])).json()
        self.assertEqual(saved["document"], document)
        jobs = await (await self.client.get("/api/jobs")).json()
        self.assertEqual(jobs["jobs"], [])

    async def test_library_floor_survives_upload_and_applies_without_rewriting_other_presets(self):
        response = await self.upload(self.first.read_bytes(), "full.sqlite3")
        self.assertEqual(response.status, 201)
        await self.select("full.sqlite3")
        document = dict(base_positive=["custom anchor"], base_negative=[], blocked_keywords=[],
                        min_tags=3, max_tags=3, pmi_threshold=0, min_cooccurrence=10, change_budget=2)
        response = await self.client.post("/api/candidate/presets", json={"name": "personal", "document": document})
        original = await response.json()
        high = vocabulary(self.root / "compact.sqlite3", minimum=1000)
        response = await self.upload(gzip.compress(high.read_bytes()), "compact.sqlite3.gz")
        self.assertEqual(response.status, 201)
        await self.select("compact.sqlite3")
        info = await (await self.client.get("/api/candidate/dataset")).json()
        self.assertEqual(info["min_cooccurrence"], 1000)
        with closing(sqlite3.connect(self.data / "libraries/compact.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT min_cooccurrence FROM dataset").fetchone()[0], 1000)
        unchanged = await (await self.client.get("/api/candidate/presets/" + original["id"])).json()
        self.assertEqual(unchanged["document"], document)

        service = self.client.server.app[APPLICATION].candidates
        with patch.object(service.store, "qualified_relations", wraps=service.store.qualified_relations) as relations:
            response = await self.client.post("/api/candidate/generate",
                                             json={"preset_id": original["id"], "mode": "fixed_seed", "seed": 7})
            self.assertEqual(response.status, 200, await response.text())
            self.assertTrue(relations.call_args_list)
            self.assertTrue(all(call.args[2] == 1000 for call in relations.call_args_list))
        # Roam's complete-combination pool shares the same preparation and effective floor.
        with patch.object(service.store, "qualified_relations", wraps=service.store.qualified_relations) as relations:
            candidates = service.provider.generate({"preset_id": original["id"], "mode": "fixed_seed", "seed": 7},
                                                   {"count": 2})
            self.assertEqual(len(candidates), 2)
            self.assertTrue(relations.call_args_list)
            self.assertTrue(all(call.args[2] == 1000 for call in relations.call_args_list))

        response = await self.client.post("/api/candidate/presets",
                                         json={"id": original["id"], "name": "personal", "document": document})
        self.assertEqual((await response.json())["document"]["min_cooccurrence"], 1000)
        higher = dict(document, min_cooccurrence=1500)
        response = await self.client.post("/api/candidate/presets",
                                         json={"id": original["id"], "name": "personal", "document": higher})
        self.assertEqual((await response.json())["document"]["min_cooccurrence"], 1500)
        await self.select("full.sqlite3")
        info = await (await self.client.get("/api/candidate/dataset")).json()
        self.assertEqual(info["min_cooccurrence"], 10)
        response = await self.client.post("/api/candidate/presets",
                                         json={"id": original["id"], "name": "personal", "document": higher})
        self.assertEqual((await response.json())["document"]["min_cooccurrence"], 1500)

    async def test_invalid_upload_and_path_keep_active_library(self):
        response = await self.upload(self.first.read_bytes(), "active.sqlite3")
        self.assertEqual(response.status, 201, await response.text())
        await self.select("active.sqlite3")
        response = await self.upload(b"not SQLite", "bad.sqlite3")
        self.assertEqual(response.status, 400, await response.text())
        response = await self.client.put("/api/candidate/library", json={"filename": "../first.sqlite3"})
        self.assertEqual(response.status, 400, await response.text())
        response = await self.client.post("/api/candidate/library", json={})
        self.assertEqual(response.status, 415)
        listing = await (await self.client.get("/api/candidate/library")).json()
        self.assertEqual(listing["selected"], "active.sqlite3")
        self.assertEqual(list(self.data.joinpath("tmp").iterdir()), [])

    async def test_refresh_reopens_replaced_file_and_clears_candidate_cache(self):
        target = self.data / "libraries" / "manual.sqlite3"
        shutil.copy2(self.first, target)
        await self.select(target.name)
        old_service = self.client.server.app[APPLICATION].candidates
        shutil.copyfile(self.second, target)
        await self.client.get("/api/candidate/library")
        new_service = self.client.server.app[APPLICATION].candidates
        self.assertIsNot(old_service, new_service)
        self.assertEqual({x["name"] for x in new_service.list_tags()["tags"]}, {"red_sky", "forest"})


if __name__ == "__main__":
    unittest.main()
