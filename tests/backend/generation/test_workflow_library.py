"""Workflow templates are local, atomic copies and never alter configured backends."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from backend.domain import ConflictError, ValidationError
from backend.store.workflow_library import MAX_BYTES, WorkflowLibrary
from backend.generation import validate_backend
from backend.host import create_app
from backend.generation.workflows import default_txt2img


def template(name="我的文生图"):
    document = default_txt2img("example.safetensors")
    return dict(document, name=name)


class WorkflowStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "data" / "workflows"
        self.library = WorkflowLibrary(self.directory, validate_backend)

    def test_save_and_read_preserve_parameter_changes_and_bindings(self):
        document = template()
        original = copy.deepcopy(document)
        document["workflow"]["5"]["inputs"].update(steps=16, cfg=4.2, sampler_name="euler")
        document["workflow"]["4"]["inputs"].update(width=832, height=1216)
        with patch("aiohttp.ClientSession.request", side_effect=AssertionError("No backend HTTP allowed")):
            record = self.library.save_as(document)
        self.assertEqual(self.library.read(record["id"]), record)
        self.assertEqual(record["workflow"]["5"]["inputs"]["cfg"], 4.2)
        self.assertEqual(record["workflow"]["4"]["inputs"]["width"], 832)
        self.assertEqual(record["bindings"], original["bindings"])
        self.assertEqual(record["output_nodes"], original["output_nodes"])
        raw = (self.directory / (record["id"] + ".json")).read_bytes()
        self.assertEqual(record["revision"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(set(p.suffix for p in self.directory.iterdir()), {".json"})
        self.assertFalse((self.directory / ".write.lock").exists())

    def test_duplicate_name_and_id_never_overwrite(self):
        original = self.library.save_as(template("Test"))
        with self.assertRaises(ConflictError):
            self.library.save_as(template("test"))
        with patch("backend.store.workflow_library.uuid.uuid4") as identity:
            identity.return_value.hex = original["id"]
            with self.assertRaises(ConflictError):
                self.library.save_as(template("Another"))
        self.assertEqual(self.library.read(original["id"]), original)
        self.assertEqual(len(self.library.listing()), 1)

    def test_validation_names_links_nonfinite_and_path_escape(self):
        for name in ("", " ", "a" * 121, "../escape", "a/b", "a\\b", "a:b", "a\nline", None, "."):
            with self.assertRaises(ValidationError, msg=str(name)):
                self.library.save_as(template(name))
        self.assertFalse(self.directory.exists())
        for identifier in ("../escape", "a" * 31, "a" * 33, None, "A" * 32):
            with self.assertRaises(ValidationError):
                self.library.read(identifier)
        for change in ("ui", "binding", "link", "output", "nan"):
            document = template()
            if change == "ui":
                document["workflow"] = {"nodes": []}
            elif change == "binding":
                document["bindings"]["positive"]["node_id"] = "missing"
            elif change == "link":
                document["workflow"]["2"]["inputs"]["text"] = ["3", 0]
            elif change == "output":
                document["output_nodes"] = ["missing"]
            else:
                document["workflow"]["5"]["inputs"]["cfg"] = float("inf")
            with self.assertRaises(ValidationError, msg=change):
                self.library.save_as(document)

    def test_failed_replace_cleans_temporary_and_lock(self):
        with patch("backend.store.workflow_library.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.library.save_as(template())
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_listing_and_invalid_record_identity(self):
        self.assertEqual(self.library.listing(), [])
        self.assertIsNone(self.library.read("0" * 32))
        first = self.library.save_as(template("B"))
        second = self.library.save_as(template("A"))
        self.assertEqual([r["id"] for r in self.library.listing()], [second["id"], first["id"]])
        self.assertEqual(set(self.library.listing()[0]), {"id", "name", "revision"})
        (self.directory / "not-a-workflow.json").write_text("{}", encoding="utf-8")
        self.assertEqual(len(self.library.listing()), 2)
        path = self.directory / (first["id"] + ".json")
        changed = json.loads(path.read_text(encoding="utf-8"))
        changed["id"] = second["id"]
        path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(ValidationError):
            self.library.read(first["id"])


class WorkflowAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addAsyncCleanup(self.cleanup_directory)
        self.directory = Path(self.temporary.name) / "data" / "workflows"
        app = create_app(self.directory.parent)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def cleanup_directory(self):
        self.temporary.cleanup()

    async def test_round_trip_and_duplicate_protection(self):
        self.assertEqual(await (await self.client.get("/api/workflows")).json(), {"workflows": []})
        response = await self.client.post("/api/workflows", json=template())
        saved = await response.json()
        self.assertEqual(response.status, 201, saved)
        self.assertEqual(set(saved), {"id", "name", "revision", "workflow", "bindings", "output_nodes"})
        loaded = await (await self.client.get("/api/workflows/" + saved["id"])).json()
        self.assertEqual(loaded, saved)
        listing = await (await self.client.get("/api/workflows")).json()
        self.assertEqual(listing["workflows"], [{key: saved[key] for key in ("id", "name", "revision")}])
        response = await self.client.post("/api/workflows", json=template())
        self.assertEqual(response.status, 409)

    async def test_missing_and_invalid_identifier(self):
        self.assertEqual((await self.client.get("/api/workflows/" + "0" * 32)).status, 404)
        self.assertEqual((await self.client.get("/api/workflows/invalid.json")).status, 400)

    async def test_json_origin_and_size_limits(self):
        for headers in ({"Origin": "https://other.example"}, {"Sec-Fetch-Site": "cross-site"},
                        {"Origin": str(self.client.make_url("/")).rstrip("/").replace("http:", "https:")}):
            response = await self.client.post("/api/workflows", json=template(), headers=headers)
            self.assertEqual(response.status, 403)
        response = await self.client.post("/api/workflows", data="{}")
        self.assertEqual(response.status, 415)
        for raw in ('{"x": NaN}', '{"name":"a","name":"b"}', '[1]', '{"x":'):
            response = await self.client.post("/api/workflows", data=raw, headers={"Content-Type": "application/json"})
            self.assertEqual(response.status, 400, await response.text())
        response = await self.client.post("/api/workflows", data=io.BytesIO(b"x" * (MAX_BYTES + 1)),
                                          headers={"Content-Type": "application/json"})
        self.assertEqual(response.status, 413)
        self.assertEqual(list(self.directory.iterdir()), [])
        response = await self.client.post("/api/workflows", json=template(),
                                          headers={"Origin": str(self.client.make_url("/")).rstrip("/")})
        self.assertEqual(response.status, 201, await response.text())


if __name__ == "__main__":
    unittest.main()
