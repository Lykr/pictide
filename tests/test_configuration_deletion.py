"""Deleting configuration preserves generation snapshots and recoverable data."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from backend.store.sqlite import encode
from test_app import FakeBackend, configuration


class ConfigurationDeletionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        fake = FakeBackend()
        self.host = create_app(self.root, lambda config, session: fake)
        self.application = self.host[APPLICATION]
        self.storage = self.application.storage
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()
        response = await self.client.put("/api/backends/local", json=dict(configuration(), workflow_mode="custom", workflow_name="Portrait"))
        self.assertEqual(response.status, 200)
        self.saved = await response.json()
        self.path = self.root / "workflows" / f"{self.saved['workflow_id']}.json"

    async def asyncTearDown(self):
        await self.client.close()
        self.temporary.cleanup()

    def old_job(self, request="deletion-history-01", complete=False):
        job = self.storage.create_job({"backend_id": "local", "request_id": request,
                                       "positive": "library", "negative": "blurry", "seed": 2})
        if complete:
            self.storage.complete(job["id"], [{"node_id": "9", "index": 0, "filename": "old.png", "subfolder": "", "type": "output"}])
        return job

    async def delete_workflow(self, payload=None, status=200):
        response = await self.client.delete("/api/workflows/" + self.saved["workflow_id"],
                                            json=payload if payload is not None else {"revision": self.saved["workflow_revision"]})
        result = await response.json()
        self.assertEqual(response.status, status, result)
        return result

    async def test_workflow_deletion_archives_and_detaches_all_current_backends(self):
        source = self.path.read_bytes()
        original = self.storage.backend("local")
        self.storage.save_backend(dict(original, id="second", name="Second backend"))
        job = self.old_job(complete=True)
        artifact = self.storage.artifacts()[0]
        self.storage.rate(artifact["id"], 1)
        deleted = await self.delete_workflow()
        self.assertEqual(deleted, {"deleted": True, "id": self.saved["workflow_id"], "detached_backends": 2})
        self.assertFalse(self.path.exists())
        archive = self.root / "workflows" / ".backups" / f"{self.saved['workflow_id']}-{self.saved['workflow_revision']}.json"
        self.assertEqual(archive.read_bytes(), source)
        for backend in self.storage.backends():
            for key in ("workflow_id", "workflow_name", "workflow_revision"):
                self.assertNotIn(key, backend)
            for key in ("workflow", "bindings", "output_nodes", "api_key"):
                self.assertEqual(backend[key], original[key])
            self.assertEqual(backend["workflow_mode"], "custom")
        self.assertEqual(self.storage.job_backend(job["id"]), original)
        self.assertEqual(self.storage.artifact(artifact["id"])["feedback"], 1)
        response = await self.client.get(artifact["image_url"])
        self.assertEqual(response.status, 200)
        self.assertEqual((await self.client.get("/api/workflows/" + self.saved["workflow_id"])).status, 404)
        self.assertEqual((await (await self.client.get("/api/workflows")).json())["workflows"], [])
        request = await self.client.post("/api/jobs", json={"backend_id": "local", "request_id": "after-template-deletion",
                                                          "positive": "garden", "negative": "blurry", "seed": 3})
        self.assertEqual(request.status, 202)

    async def test_workflow_deletion_requires_current_revision(self):
        await self.delete_workflow({}, status=400)
        await self.delete_workflow({"revision": "0" * 64}, status=409)
        self.assertTrue(self.path.is_file())
        self.assertEqual(self.storage.backend("local")["workflow_id"], self.saved["workflow_id"])

    async def test_workflow_delete_database_failure_restores_file_and_all_associations(self):
        source = self.path.read_bytes()
        original = self.storage.backend("local")
        self.storage.save_backend(dict(original, id="second", name="Second backend"))
        calls = 0
        def fail_second_write(value):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("second backend transaction failed")
            return encode(value)
        with patch("backend.store.sqlite.encode", side_effect=fail_second_write):
            with self.assertRaises(OSError):
                await self.application.delete_workflow(self.saved["workflow_id"], {"revision": self.saved["workflow_revision"]})
        self.assertEqual(self.path.read_bytes(), source)
        self.assertEqual(len(self.application.workflows.listing()), 1)
        for backend in self.storage.backends():
            self.assertEqual(backend["workflow_id"], self.saved["workflow_id"])
            self.assertEqual(backend["workflow_revision"], self.saved["workflow_revision"])

    async def test_workflow_delete_backup_failure_never_detaches_backends(self):
        with patch("backend.store.workflow_library.os.replace", side_effect=OSError("backup disk failure")), \
                patch.object(self.storage, "detach_workflow", wraps=self.storage.detach_workflow) as detach:
            with self.assertRaises(OSError):
                await self.application.delete_workflow(self.saved["workflow_id"], {"revision": self.saved["workflow_revision"]})
        detach.assert_not_called()
        self.assertTrue(self.path.is_file())
        self.assertEqual(self.storage.backend("local")["workflow_id"], self.saved["workflow_id"])

    async def test_deleting_backend_preserves_jobs_images_keys_and_recoverable_revision(self):
        original = self.storage.backend("local")
        job = self.old_job(complete=True)
        artifact = self.storage.artifacts()[0]
        response = await self.client.delete("/api/backends/local", json={})
        result = await response.json()
        self.assertEqual(response.status, 200, result)
        self.assertEqual(result, {"deleted": True, "id": "local"})
        self.assertNotIn(configuration()["api_key"], json.dumps(result))
        self.assertIsNone(self.storage.backend("local"))
        self.assertEqual(self.storage.backends(), [])
        self.assertEqual(self.storage.job_backend(job["id"]), original)
        self.assertEqual(self.storage.job(job["id"])["status"], "completed")
        self.assertEqual((await self.client.get(artifact["image_url"])).status, 200)
        with self.storage.connection() as database:
            record = database.execute("SELECT config FROM backend_revisions WHERE backend_id='local' ORDER BY created_at DESC LIMIT 1").fetchone()
        self.assertEqual(json.loads(record["config"]), original)
        self.assertTrue(self.path.is_file())
        response = await self.client.post("/api/jobs", json={"backend_id": "local", "request_id": "after-backend-deletion",
                                                          "positive": "garden", "negative": "blurry", "seed": 3})
        self.assertEqual(response.status, 400)
        self.assertEqual((await self.client.delete("/api/backends/local", json={})).status, 404)

    async def test_backend_deletion_does_not_cancel_existing_queued_job(self):
        job = self.old_job()
        response = await self.client.delete("/api/backends/local", json={})
        self.assertEqual(response.status, 200)
        self.assertEqual(self.storage.job(job["id"])["status"], "queued")
        self.assertEqual(self.storage.job_backend(job["id"])["api_key"], configuration()["api_key"])
        self.application.tasks.wake.set()
        for _ in range(100):
            if self.storage.job(job["id"])["status"] == "completed":
                break
            await asyncio.sleep(.02)
        self.assertEqual(self.storage.job(job["id"])["status"], "completed")

    async def test_delete_endpoints_enforce_json_and_origin_boundaries(self):
        paths = ["/api/backends/local", "/api/workflows/" + self.saved["workflow_id"]]
        for path in paths:
            self.assertEqual((await self.client.delete(path, json={}, headers={"Origin": "https://other.invalid"})).status, 403)
            self.assertEqual((await self.client.delete(path, data="{}")).status, 415)
        self.assertTrue(self.path.is_file())
        self.assertIsNotNone(self.storage.backend("local"))

    async def test_deleted_template_name_can_be_used_for_a_new_template(self):
        await self.delete_workflow()
        response = await self.client.put("/api/backends/local", json=dict(configuration(), workflow_mode="custom", workflow_name="Portrait"))
        result = await response.json()
        self.assertEqual(response.status, 200, result)
        self.assertNotEqual(result["workflow_id"], self.saved["workflow_id"])
        self.assertEqual(len(self.application.workflows.listing()), 1)


if __name__ == "__main__":
    unittest.main()
