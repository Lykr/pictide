"""Generated gallery removals use the shared durable cleanup boundary."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.domain import ValidationError
from backend.host import APPLICATION, create_app
from backend.paths import DataPaths
from backend.store.cleanup import delete_pending
from backend.store.sqlite import Repository
from backend.task.assets import cache_output
from test_app import FakeBackend, configuration
from test_cleanup import CleanupFixture


class GeneratedStorageTests(CleanupFixture, unittest.TestCase):
    def test_single_unliked_removes_files_and_preserves_history(self):
        iid, image, job = self.artifact()
        result = self.repo.clear_generated(iid)
        self.assertEqual(result, {"removed": 1, "hidden": 0, "revision": 1})
        self.assertIsNone(self.repo.artifact(iid))
        self.assertIsNone(self.repo.artifact_source(iid))
        self.assertEqual(self.repo.job(job["id"])["status"], "completed")
        with self.assertRaises(ValidationError):
            self.repo.rate(iid, 1)
        self.assertEqual(delete_pending(self.repo, self.paths, 100), 1)
        self.assertFalse(image.exists())
        self.assertFalse(image.with_suffix(".json").exists())
        self.assertEqual(self.repo.clear_generated(iid), {"removed": 0, "hidden": 0, "revision": 1})
        self.assertEqual(self.repo.clear_generated("missing"), {"removed": 0, "hidden": 0, "revision": 1})

    def test_liked_hidden_persists_and_remains_accessible(self):
        iid, image, _ = self.artifact()
        self.repo.rate(iid, 1)
        self.assertEqual(self.repo.clear_generated(iid), {"removed": 0, "hidden": 1, "revision": 1})
        repo = Repository(self.paths.database)
        self.assertIsNotNone(repo.artifact(iid)["generated_hidden_at"])
        self.assertEqual(repo.artifact(iid)["feedback"], 1)
        self.assertIsNotNone(repo.artifact_source(iid))
        self.assertEqual(repo.artifacts(source="generate"), [])
        self.assertEqual(len(repo.artifacts(liked=True)), 1)
        self.assertEqual(repo.counts(), {"artifacts": 1, "generate": 0, "roam": 0, "liked": 1})
        self.assertEqual(delete_pending(repo, self.paths, 100), 0)
        self.assertTrue(image.exists())
        self.assertTrue(image.with_suffix(".json").exists())
        self.assertEqual(repo.clear_generated(iid)["revision"], 1)
        # Withdrawing later does not restore a dismissed generated result.
        repo.rate(iid, None)
        self.assertEqual(repo.artifacts(source="generate"), [])
        self.assertEqual(repo.expire_artifacts("2999-01-01T00:00:00Z"), 1)
        self.assertEqual(repo.artifact_revision(), 2)

    def test_other_actor_likes_protect_and_snapshot_covers_more_than_page(self):
        job = self.repo.create_job({"request_id": "many", "backend_id": "test", "positive": "p", "negative": "n", "seed": 1})
        self.repo.complete(job["id"], [{"node_id": "9", "index": n} for n in range(205)])
        iid = self.repo.artifacts()[0]["id"]
        with self.repo.connection() as db:
            db.execute("INSERT INTO feedback VALUES (?,'another',1,'2026-01-01')", (iid,))
        self.assertEqual(self.repo.clear_generated(), {"removed": 204, "hidden": 1, "revision": 205})
        self.assertIsNotNone(self.repo.artifact(iid))
        self.assertIsNone(self.repo.artifact(iid)["feedback"])
        self.assertEqual(self.repo.artifact_page(source="generate")["total"], 0)
        self.assertEqual(self.repo.clear_generated()["revision"], 205)
        # Outputs finishing after the snapshot remain visible.
        fresh = self.artifact()[0]
        self.assertEqual([a["id"] for a in self.repo.artifacts(source="generate")], [fresh])

    def test_roam_rejected_and_bulk_does_not_touch_roam(self):
        roam, image, job = self.artifact()
        with self.repo.connection() as db:
            db.execute("INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)", (job["id"], "epoch", "{}", "2026-01-01"))
        generated = self.artifact()[0]
        with self.assertRaises(ValidationError):
            self.repo.clear_generated(roam)
        self.assertEqual(self.repo.clear_generated()["removed"], 1)
        self.assertIsNone(self.repo.artifact(generated))
        self.assertEqual([a["id"] for a in self.repo.artifacts(source="roam")], [roam])
        self.assertTrue(image.exists())

    def test_hidden_cursor_and_revision_keep_page_consistent(self):
        older = self.artifact("2026-01-01T00:00:00Z")[0]
        middle = self.artifact("2026-01-02T00:00:00Z")[0]
        newest = self.artifact("2026-01-03T00:00:00Z")[0]
        first = self.repo.artifact_page(source="generate", limit=1)
        self.assertEqual(first["next_cursor"], newest)
        self.repo.rate(newest, 1)
        self.repo.clear_generated(newest)
        self.repo.clear_generated(middle)
        page = self.repo.artifact_page(source="generate", before=newest, limit=1)
        self.assertEqual([a["id"] for a in page["artifacts"]], [older])
        self.assertEqual(page["revision"], 2)
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["counts"]["generate"], 1)
        self.assertEqual(len(self.repo.artifacts()), 2)

    def test_late_cache_and_completion_do_not_revive_removed_or_hidden(self):
        iid, image, job = self.artifact()
        self.repo.clear_generated(iid)
        output = {"node_id": "7", "index": 0, "local_path": "images/late.png", "content_type": "image/png"}
        self.assertFalse(self.repo.cache_artifact(iid, output))
        self.repo.complete(job["id"], [output])
        self.assertEqual(self.repo.cleanup_counts()["pending"], 2)
        liked, _, liked_job = self.artifact()
        self.repo.rate(liked, 1)
        self.repo.clear_generated(liked)
        self.assertTrue(self.repo.cache_artifact(liked, output))
        self.repo.complete(liked_job["id"], [output])
        self.assertEqual(self.repo.artifacts(source="generate"), [])
        self.assertEqual(self.repo.artifact(liked)["feedback"], 1)

    def test_file_failure_retries_and_unsafe_path_stays_untouched(self):
        iid, image, _ = self.artifact()
        self.repo.clear_generated(iid)
        original = Path.unlink
        def locked(target, *args, **kwargs):
            if target == image:
                raise PermissionError("locked")
            return original(target, *args, **kwargs)
        with patch.object(Path, "unlink", locked):
            self.assertEqual(delete_pending(self.repo, self.paths, 100), 0)
        self.assertEqual(Repository(self.paths.database).cleanup_counts()["pending"], 1)
        self.assertEqual(delete_pending(self.repo, self.paths, 100), 1)
        unsafe, _, _ = self.artifact()
        outside = self.paths.root / "preserve.png"
        outside.write_bytes(b"safe")
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET local_path='../preserve.png' WHERE id=?", (unsafe,))
        self.repo.clear_generated(unsafe)
        self.assertEqual(delete_pending(self.repo, self.paths, 100), 0)
        self.assertTrue(outside.exists())

    def test_shared_files_are_retained_for_hidden_likes(self):
        removed, image, _ = self.artifact(path="shared.png")
        liked, _, _ = self.artifact(path="shared.png")
        self.repo.rate(liked, 1)
        self.repo.clear_generated()
        self.assertEqual(delete_pending(self.repo, self.paths, 100), 0)
        self.assertTrue(image.exists())
        self.assertTrue(image.with_suffix(".json").exists())
        self.assertIsNone(self.repo.artifact(removed))
        self.assertIsNotNone(self.repo.artifact(liked))


class GeneratedApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.paths = DataPaths(self.directory.name).ensure()
        self.backend = FakeBackend()
        self.app = create_app(self.paths.root, lambda config, session: self.backend)
        self.application = self.app[APPLICATION]
        self.application.history.save(0)
        self.repo = self.application.storage
        self.repo.save_backend(dict(configuration(), id="local"))
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.number = 0

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def artifact(self, liked=False):
        self.number += 1
        job = self.repo.create_job({"request_id": f"gallery-{self.number}", "backend_id": "local", "positive": "quiet garden", "negative": "watermark", "seed": 1})
        output = await cache_output(self.paths, self.backend, {"node_id": "9", "index": 0, "filename": "sample.png", "subfolder": "", "type": "output"}, job)
        self.repo.complete(job["id"], [output])
        artifact = next(row for row in self.repo.artifacts() if row["job_id"] == job["id"])
        if liked:
            self.repo.rate(artifact["id"], 1)
        return artifact, self.paths.root / output["local_path"]

    async def test_bulk_route_likes_stay_downloadable_and_unliked_are_gone(self):
        kept, kept_path = await self.artifact(True)
        removed, removed_path = await self.artifact()
        result = await self.client.delete("/api/generated", json={})
        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {"removed": 1, "hidden": 1, "revision": 2, "pending_files": 0})
        self.assertFalse(removed_path.exists())
        self.assertFalse(removed_path.with_suffix(".json").exists())
        self.assertTrue(kept_path.exists())
        self.assertEqual((await self.client.get(kept["image_url"])).status, 200)
        prompts = await self.client.get(f"/api/artifacts/{kept['id']}/prompts")
        self.assertEqual(await prompts.json(), {"positive": "quiet garden", "negative": "watermark"})
        self.assertEqual((await self.client.get(removed["image_url"])).status, 404)
        self.assertEqual((await self.client.get(f"/api/artifacts/{removed['id']}/prompts")).status, 404)
        generated = await (await self.client.get("/api/artifacts?source=generate")).json()
        self.assertEqual(generated["total"], 0)
        liked = await (await self.client.get("/api/artifacts?liked=1")).json()
        self.assertEqual([a["id"] for a in liked["artifacts"]], [kept["id"]])
        self.assertEqual((await (await self.client.get("/api/bootstrap")).json())["artifact_revision"], 2)
        self.assertEqual((await (await self.client.get("/api/settings/history")).json())["artifact_revision"], 2)
        # Late feedback contains the hidden flag and the same visibility revision.
        response = await self.client.put(f"/api/artifacts/{kept['id']}/feedback", json={"value": 1})
        feedback = await response.json()
        self.assertIsNotNone(feedback["artifact"]["generated_hidden_at"])
        self.assertEqual(feedback["artifact_revision"], 2)

    async def test_single_route_validation_idempotence_and_roam_boundary(self):
        artifact, path = await self.artifact()
        route = f"/api/generated/{artifact['id']}"
        self.assertEqual((await self.client.delete(route, json={"source": "all"})).status, 400)
        self.assertTrue(path.exists())
        self.assertEqual((await (await self.client.delete(route, json={})).json())["removed"], 1)
        self.assertEqual((await (await self.client.delete(route, json={})).json())["removed"], 0)
        self.assertEqual((await (await self.client.delete("/api/generated/missing", json={})).json())["removed"], 0)
        roam, roam_path = await self.artifact()
        with self.repo.connection() as db:
            db.execute("INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)", (roam["job_id"], "epoch", "{}", "2026-01-01"))
        self.assertEqual((await self.client.delete(f"/api/generated/{roam['id']}", json={})).status, 400)
        self.assertTrue(roam_path.exists())

    async def test_late_image_cache_cannot_undo_deletion(self):
        artifact, path = await self.artifact()
        path.unlink()
        path.with_suffix(".json").unlink()
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET local_path=NULL WHERE id=?", (artifact["id"],))
        original = self.backend.image
        async def delayed(output):
            self.repo.clear_generated(artifact["id"])
            return await original(output)
        self.backend.image = delayed
        self.assertEqual((await self.client.get(artifact["image_url"])).status, 404)
        self.assertEqual(self.repo.artifacts(source="generate"), [])
        await self.client.delete("/api/generated", json={})
        self.assertFalse(path.exists())
        self.assertFalse(path.with_suffix(".json").exists())

    async def test_pending_retry_does_not_apply_retention_policy(self):
        artifact, path = await self.artifact()
        original = Path.unlink
        def locked(target, *args, **kwargs):
            if target == path:
                raise PermissionError("locked")
            return original(target, *args, **kwargs)
        with patch.object(Path, "unlink", locked):
            response = await self.client.delete(f"/api/generated/{artifact['id']}", json={})
            self.assertEqual((await response.json())["pending_files"], 1)
        untouched, untouched_path = await self.artifact()
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET created_at='2000-01-01' WHERE id=?", (untouched["id"],))
        self.application.history.save(1)
        # Retry only the requested removal, rather than expiring unrelated images.
        response = await self.client.delete(f"/api/generated/{artifact['id']}", json={})
        self.assertEqual((await response.json())["pending_files"], 0)
        self.assertTrue(untouched_path.exists())
        self.assertFalse(path.exists())
