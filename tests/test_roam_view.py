"""Durable roam cursors and contiguous windows do not depend on browser state."""
from pathlib import Path
import tempfile
import unittest

from backend.domain import NotFoundError, ValidationError
from backend.store.sqlite import Repository


class RoamViewStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Repository(Path(self.temporary.name) / "pictide.sqlite3")
        self.repo.save_backend({"id": "local", "name": "test", "workflow": {}})
        self.payload = {"request_id": "roam-view-fixture", "backend_id": "local", "positive": "landscape", "negative": "", "seed": 1}

    def images(self, count=500, roam=True):
        job = self.repo.create_job({**self.payload, "request_id": self.payload["request_id"] + str(roam)})
        self.repo.complete(job["id"], [{"node_id": "9", "index": n} for n in range(count)])
        with self.repo.connection() as db:
            if roam:
                db.execute("INSERT INTO roam_jobs VALUES (?,'fixture','{}','2026-10-14')", (job["id"],))
            rows = db.execute("SELECT id FROM artifacts WHERE job_id=? ORDER BY output_index", (job["id"],)).fetchall()
            for n, row in enumerate(rows):
                db.execute("UPDATE artifacts SET id=?,created_at='2026-10-14T12:00:00+00:00' WHERE id=?", (f"{'r' if roam else 'g'}-{n:04}", row["id"]))
        return [f"{'r' if roam else 'g'}-{n:04}" for n in range(count)]

    def test_cursor_survives_restart_and_ignores_late_writes(self):
        ids = self.images(3)
        self.assertEqual(self.repo.roam_view(), {"artifact_id": None, "viewed_at": 0})
        self.repo.roam_view({"artifact_id": ids[0], "viewed_at": 100})
        self.repo.roam_view({"artifact_id": ids[2], "viewed_at": 200})
        for timestamp in (199, 200):
            self.assertEqual(self.repo.roam_view({"artifact_id": ids[1], "viewed_at": timestamp}), {"artifact_id": ids[2], "viewed_at": 200})
        self.assertEqual(Repository(self.repo.path).roam_view(), {"artifact_id": ids[2], "viewed_at": 200})
        self.assertEqual(self.repo.roam_view({"artifact_id": None, "viewed_at": 201}), {"artifact_id": None, "viewed_at": 201})

    def test_cursor_validates_source_id_and_timestamp_without_clobbering(self):
        ids = self.images(1)
        generated = self.images(1, False)[0]
        saved = self.repo.roam_view({"artifact_id": ids[0], "viewed_at": 100})
        for identifier in (generated, "missing"):
            with self.assertRaises(NotFoundError):
                self.repo.roam_view({"artifact_id": identifier, "viewed_at": 101})
        for timestamp in (None, True, -1, "100", 1.2, 2**53):
            with self.assertRaises(ValidationError):
                self.repo.roam_view({"artifact_id": ids[0], "viewed_at": timestamp})
        with self.assertRaises(ValidationError):
            self.repo.roam_view({"viewed_at": 101})
        self.assertEqual(self.repo.roam_view(), saved)

    def test_removed_cursor_returns_nearest_older_then_newer_then_empty(self):
        ids = self.images(5)
        self.repo.roam_view({"artifact_id": ids[2], "viewed_at": 100})
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET deleted_at='removed' WHERE id=?", (ids[2],))
        self.assertEqual(self.repo.roam_view(), {"artifact_id": ids[1], "viewed_at": 100})
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET deleted_at='removed' WHERE id<?", (ids[2],))
        self.assertEqual(self.repo.roam_view()["artifact_id"], ids[3])
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET deleted_at='removed'")
        self.assertIsNone(self.repo.roam_view()["artifact_id"])

    def test_around_old_cursor_is_contiguous_over_200_with_timestamp_ties(self):
        ids = self.images()
        self.images(10, False)
        page = self.repo.artifact_page(source="roam", around=ids[250])
        self.assertEqual([item["id"] for item in page["artifacts"]], list(reversed(ids[151:351])))
        self.assertEqual(page["anchor_id"], ids[250])
        self.assertTrue(page["has_newer"])
        self.assertTrue(page["has_more"])
        self.assertEqual(page["total"], 500)
        self.assertEqual(page["next_cursor"], ids[151])
        for index in (0, 499):
            boundary = self.repo.artifact_page(source="roam", around=ids[index])
            self.assertEqual(len(boundary["artifacts"]), 200)
            self.assertEqual(boundary["has_newer"], index == 0)
            self.assertEqual(boundary["has_more"], index == 499)
            self.assertIn(ids[index], [item["id"] for item in boundary["artifacts"]])

    def test_around_fallback_and_small_window_boundary(self):
        ids = self.images(8)
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET deleted_at='removed' WHERE id=?", (ids[4],))
        page = self.repo.artifact_page(source="roam", around=ids[4], limit=3)
        self.assertEqual(page["anchor_id"], ids[3])
        self.assertEqual([item["id"] for item in page["artifacts"]], [ids[5], ids[3], ids[2]])
        self.assertEqual(self.repo.artifact_page(source="roam", around="unknown")["anchor_id"], ids[-1])
        single = self.repo.artifact_page(source="roam", around=ids[3], limit=1)
        self.assertEqual([item["id"] for item in single["artifacts"]], [ids[3]])
        self.assertTrue(single["has_newer"])
        self.assertTrue(single["has_more"])
        self.assertEqual(single["next_cursor"], ids[3])
        for options in ({"source": "all"}, {"source": "generate"}, {"source": "roam", "liked": True}, {"source": "roam", "before": ids[7]}):
            with self.assertRaises(ValidationError):
                self.repo.artifact_page(around=ids[3], **options)


if __name__ == "__main__":
    unittest.main()
