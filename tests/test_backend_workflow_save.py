"""Workflow edits retain identity while jobs keep immutable backend snapshots."""
import asyncio
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from test_app import FakeBackend, configuration


class BackendWorkflowSaveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        fake = FakeBackend()
        self.host = create_app(self.root, lambda config, session: fake)
        self.application = self.host[APPLICATION]
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temporary.cleanup()

    def draft(self, name="Portrait"):
        return dict(configuration(), workflow_mode="custom", workflow_name=name)

    async def save(self, draft=None, status=200):
        response = await self.client.put("/api/backends/local", json=draft or self.draft())
        result = await response.json()
        self.assertEqual(response.status, status, result)
        return result

    async def templates(self):
        return (await (await self.client.get("/api/workflows")).json())["workflows"]

    async def test_new_custom_template_and_backend_share_content_and_identity(self):
        saved = await self.save()
        record = await (await self.client.get("/api/workflows/" + saved["workflow_id"])).json()
        self.assertEqual(saved["workflow_revision"], record["revision"])
        self.assertEqual(saved["workflow_name"], record["name"])
        for key in ("workflow", "bindings", "output_nodes"):
            self.assertEqual(saved[key], record[key])
        self.assertNotIn("api_key", saved)
        self.assertTrue(saved["has_api_key"])
        self.assertEqual(len(await self.templates()), 1)

    async def test_retry_reuses_normalized_name_and_content(self):
        first = await self.save()
        repeated = await self.save(self.draft(" portrait "))
        self.assertEqual(repeated["workflow_id"], first["workflow_id"])
        self.assertEqual(repeated["workflow_name"], "Portrait")
        self.assertEqual(len(await self.templates()), 1)
        self.assertEqual(len(list((self.root / "workflows").glob("*.json"))), 1)

    async def test_selected_template_reuses_revision_and_preserves_private_key(self):
        first = await self.save()
        draft = {key: value for key, value in first.items() if key != "has_api_key"}
        saved = await self.save(draft)
        self.assertEqual(saved["workflow_id"], first["workflow_id"])
        self.assertEqual(self.application.storage.backend("local")["api_key"], configuration()["api_key"])
        self.assertEqual(len(await self.templates()), 1)

    async def test_name_conflict_leaves_backend_and_template_unchanged(self):
        first = await self.save()
        await self.client.put("/api/backends/other", json=self.draft("Other"))
        draft = copy.deepcopy(first)
        draft["workflow_name"] = "Other"
        draft["workflow"]["3"]["inputs"]["seed"] = 23
        draft["base_url"] = "http://127.0.0.1:9999"
        result = await self.save(draft, status=409)
        self.assertIn("其他工作流", result["error"])
        self.assertEqual(self.application.storage.backend("local")["base_url"], configuration()["base_url"])
        self.assertEqual(len(await self.templates()), 2)
        record = self.application.workflows.read(first["workflow_id"])
        self.assertEqual(record["workflow"]["3"]["inputs"]["seed"], 0)

    async def test_modified_selected_template_retains_id_and_preserves_old_job(self):
        first = await self.save()
        job = self.application.storage.create_job({"backend_id": "local", "request_id": "snapshot-01",
                                                   "positive": "library", "negative": "blurry", "seed": 2})
        draft = copy.deepcopy(first)
        draft["workflow_name"] = "Portrait 2"
        draft["workflow"]["3"]["inputs"]["seed"] = 23
        saved = await self.save(draft)
        self.assertEqual(saved["workflow_id"], first["workflow_id"])
        self.assertNotEqual(saved["workflow_revision"], first["workflow_revision"])
        self.assertEqual(len(await self.templates()), 1)
        self.assertEqual(self.application.storage.job_backend(job["id"])["workflow_id"], first["workflow_id"])
        self.assertEqual(self.application.storage.job_backend(job["id"])["workflow"]["3"]["inputs"]["seed"], 0)
        self.assertEqual(self.application.workflows.read(first["workflow_id"])["workflow"]["3"]["inputs"]["seed"], 23)
        archive = self.root / "workflows" / ".backups" / f"{first['workflow_id']}-{first['workflow_revision']}.json"
        self.assertTrue(archive.is_file())

    async def test_same_name_selected_edit_updates_in_place_and_checks_revision(self):
        first = await self.save()
        draft = copy.deepcopy(first)
        draft["workflow"]["3"]["inputs"]["seed"] = 42
        updated = await self.save(draft)
        self.assertEqual(updated["workflow_id"], first["workflow_id"])
        self.assertEqual(updated["workflow_name"], first["workflow_name"])
        await self.save(draft, status=409)
        self.assertEqual(self.application.workflows.read(first["workflow_id"])["revision"], updated["workflow_revision"])
        self.assertEqual(len(await self.templates()), 1)

    async def test_selected_update_database_failure_restores_exact_previous_revision(self):
        first = await self.save()
        path = self.root / "workflows" / f"{first['workflow_id']}.json"
        previous = path.read_bytes()
        draft = copy.deepcopy(first)
        draft["workflow"]["3"]["inputs"]["seed"] = 99
        with patch("backend.store.sqlite.encode", side_effect=OSError("database write failed")):
            with self.assertRaises(OSError):
                await self.application.save_backend("local", draft)
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(self.application.workflows.read(first["workflow_id"])["revision"], first["workflow_revision"])
        self.assertEqual(self.application.storage.backend("local")["workflow_revision"], first["workflow_revision"])

    async def test_backup_failure_does_not_change_selected_template_or_backend(self):
        first = await self.save()
        draft = copy.deepcopy(first)
        draft["workflow"]["3"]["inputs"]["seed"] = 77
        with patch("backend.store.workflow_library.os.replace", side_effect=OSError("backup write failed")):
            with self.assertRaises(OSError):
                await self.application.save_backend("local", draft)
        self.assertEqual(self.application.workflows.read(first["workflow_id"])["revision"], first["workflow_revision"])
        self.assertEqual(self.application.storage.backend("local")["workflow_revision"], first["workflow_revision"])

    async def test_stale_or_missing_selected_template_never_saves_backend(self):
        first = await self.save()
        draft = dict(first, workflow_revision="0" * 64, workflow_name="New portrait")
        await self.save(draft, status=409)
        draft.update(workflow_id="0" * 32)
        await self.save(draft, status=404)
        self.assertEqual(self.application.storage.backend("local")["workflow_id"], first["workflow_id"])
        self.assertEqual(len(await self.templates()), 1)

    async def test_default_removes_template_reference_without_creating_or_deleting_templates(self):
        first = await self.save()
        draft = dict(first, workflow_mode="default")
        saved = await self.save(draft)
        self.assertEqual(saved["workflow_mode"], "default")
        self.assertNotIn("workflow_id", saved)
        self.assertNotIn("workflow_name", saved)
        self.assertNotIn("workflow_revision", saved)
        self.assertEqual(len(await self.templates()), 1)
        self.assertIsNotNone(self.application.workflows.read(first["workflow_id"]))

    async def test_invalid_name_and_revision_without_id_leave_no_template(self):
        await self.save(self.draft(""), status=400)
        await self.save(dict(self.draft(), workflow_revision="0" * 64), status=400)
        self.assertEqual(await self.templates(), [])
        self.assertIsNone(self.application.storage.backend("local"))

    async def test_database_failure_rolls_back_new_template_and_existing_backend(self):
        first = await self.save()
        with patch("backend.store.sqlite.encode", side_effect=OSError("database write failed")):
            with self.assertRaises(OSError):
                await self.application.save_backend("local", self.draft("New portrait"))
        self.assertEqual(self.application.storage.backend("local")["workflow_id"], first["workflow_id"])
        self.assertEqual(len(await self.templates()), 1)
        self.assertEqual([path.suffix for path in (self.root / "workflows").iterdir()], [".json"])

    async def test_file_failure_does_not_commit_backend(self):
        with patch("backend.store.workflow_library.os.replace", side_effect=OSError("disk write failed")), \
                patch.object(self.application.storage, "save_backend", wraps=self.application.storage.save_backend) as persist:
            with self.assertRaises(OSError):
                await self.application.save_backend("local", self.draft())
        persist.assert_not_called()
        self.assertIsNone(self.application.storage.backend("local"))
        self.assertEqual(await self.templates(), [])
        self.assertEqual(list((self.root / "workflows").iterdir()), [])

    async def test_database_failure_when_reusing_does_not_remove_existing_template(self):
        first = await self.save()
        with patch.object(self.application.storage, "save_backend", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                await self.application.save_backend("local", first)
        self.assertEqual(self.application.workflows.read(first["workflow_id"])["revision"], first["workflow_revision"])
        self.assertEqual(len(await self.templates()), 1)

    async def test_concurrent_retries_create_one_template(self):
        first, second = await asyncio.gather(self.application.save_backend("local", self.draft()),
                                             self.application.save_backend("local", self.draft()))
        self.assertEqual(first["workflow_id"], second["workflow_id"])
        self.assertEqual(len(await self.templates()), 1)


if __name__ == "__main__":
    unittest.main()
