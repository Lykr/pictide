from io import BytesIO
import json
import tempfile
import unittest
import zipfile

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from tests.backend.application.test_app import FakeBackend, configuration


class UserDataHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app(self.temporary.name, lambda config, session: FakeBackend())
        application = self.app[APPLICATION]
        application.storage.save_backend({**configuration(), "id": "fixture"})
        job = application.storage.create_job({
            "request_id": "user-data-http",
            "backend_id": "fixture",
            "positive": "garden",
            "negative": "",
            "seed": 7,
        })
        image = application.paths.images / "liked.png"
        image.write_bytes(b"liked-image")
        application.storage.complete(job["id"], [{
            "node_id": "9",
            "index": 0,
            "local_path": image.relative_to(application.paths.root).as_posix(),
            "content_type": "image/png",
        }])
        artifact = next(item for item in application.storage.artifacts() if item["job_id"] == job["id"])
        application.storage.rate(artifact["id"], 1)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temporary.cleanup()

    async def test_export_and_import_are_local_management_routes(self):
        bootstrap = await (await self.client.get("/api/bootstrap")).json()
        self.assertTrue(bootstrap["capabilities"]["user_data"])

        exported = await self.client.get("/api/user-data/export")
        self.assertEqual(exported.status, 200)
        self.assertIn("pictide-user-data-", exported.headers["Content-Disposition"])
        archive = await exported.read()
        with zipfile.ZipFile(BytesIO(archive)) as bundle:
            self.assertEqual(json_manifest(bundle)["counts"]["liked_images"], 1)

        imported = await self.client.post("/api/user-data/import", data=archive,
                                          headers={"Content-Type": "application/zip"})
        self.assertEqual(imported.status, 200)
        result = await imported.json()
        self.assertEqual((result["liked_imported"], result["liked_skipped"]), (0, 1))
        self.assertTrue((self.app[APPLICATION].paths.root / result["backup"]).is_file())
        self.assertEqual(list(self.app[APPLICATION].paths.tmp.glob("user-data-*.zip")), [])
        self.assertEqual(list(self.app[APPLICATION].paths.tmp.glob("user-data-import-*.zip")), [])


def json_manifest(archive):
    return json.loads(archive.read("manifest.json"))


if __name__ == "__main__":
    unittest.main()
