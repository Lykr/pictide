"""Targeted durable roam-mode and stale-prefetch smoke checks."""
import json
import sqlite3
import tempfile
import unittest

from backend.domain import ValidationError
from backend.paths import DataPaths
from backend.store.roam_settings import RoamSettings
from backend.store.sqlite import Repository


class RoamModesStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.paths = DataPaths(self.directory.name).ensure()
        self.repo = Repository(self.paths.database)
        self.settings = RoamSettings(self.paths)
        self.repo.save_backend({"id": "local", "name": "Local", "kind": "comfyui",
                                "base_url": "http://localhost:8188", "api_key": "", "workflow": {}})
        self.original = self.settings.save(5, "local", "preset", 20, 9)
        self.number = 0

    def job(self, epoch=None, status="queued", completed=False):
        self.number += 1
        job = self.repo.create_job({"request_id": f"mode-smoke-{self.number:03d}", "backend_id": "local",
                                   "positive": f"garden {self.number}", "negative": "blurry", "seed": self.number})
        snapshot = {"candidate_id": f"candidate-{self.number}", "positive": "ignored snapshot text",
                    "negative": "ignored", "terms": [{"text": f"garden {self.number}", "channel": "positive"}]}
        if epoch:
            with self.repo.connection() as db:
                db.execute("INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)",
                           (job["id"], epoch, json.dumps(snapshot), f"2026-10-17T00:00:{self.number:02d}"))
        self.repo.update_job(job["id"], status)
        if completed:
            self.repo.complete(job["id"], [{"node_id": "9", "index": 0, "local_path": f"keep-{self.number}.png"}])
            image = next(a for a in self.repo.artifacts() if a["job_id"] == job["id"])
            return job, image
        return job

    def test_switch_discards_only_future_roam_and_late_results_stay_hidden(self):
        epoch = self.original["epoch"]
        _, older = self.job(epoch, completed=True)
        _, current = self.job(epoch, completed=True)
        _, future = self.job(epoch, completed=True)
        self.repo.rate(future["id"], 1)
        self.repo.roam_view({"artifact_id": current["id"], "viewed_at": 1})
        queued = self.job(epoch)
        running = self.job(epoch)
        self.assertTrue(self.repo.claim_job(running["id"]))
        self.repo.attach_prompt(running["id"], "claimed-before-switch")
        self.repo.update_job(running["id"], "running")
        accepted = self.job(epoch)
        self.repo.attach_prompt(accepted["id"], "external-id")
        unknown = self.job(epoch, "unknown")
        manual = self.job()
        revision = self.repo.artifact_revision()
        changed = self.settings.save_options(prompt_mode="along")
        self.assertNotEqual(changed["epoch"], epoch)
        self.assertEqual(changed["prompt_mode"], "along")
        self.assertEqual(self.repo.roam_view()["artifact_id"], current["id"])
        self.assertEqual({a["id"] for a in self.repo.artifacts(source="roam")}, {older["id"], current["id"]})
        self.assertEqual([a["id"] for a in self.repo.artifacts(liked=True)], [future["id"]])
        self.assertEqual(self.repo.artifact(future["id"])["local_path"], future["local_path"])
        self.assertEqual(self.repo.artifact_revision(), revision + 1)
        self.assertEqual(self.repo.job(queued["id"])["status"], "cancelled")
        self.assertFalse(self.repo.claim_job(queued["id"]))
        self.assertEqual(self.repo.job(manual["id"])["status"], "queued")
        self.assertEqual(self.repo.job(accepted["id"])["status"], "queued")
        state = self.repo.ensure_roam(epoch, current["id"], 5)
        self.assertFalse(state["paused"])
        self.assertEqual(state["roam_pending"], 0)
        self.assertEqual(state["pending"], 3)  # Accepted old work and manual work still exist.
        restarted = Repository(self.paths.database)
        restarted.complete(running["id"], [{"node_id": "9", "index": 0, "local_path": "late.png"}])
        self.assertEqual(restarted.job(running["id"])["status"], "completed")
        self.assertEqual(len(restarted.artifacts(source="roam")), 2)
        self.assertEqual(restarted.counts()["artifacts"], 4)
        with restarted.connection() as db:
            self.assertIsNotNone(db.execute("SELECT roam_hidden_at FROM artifacts WHERE job_id=?", (running["id"],)).fetchone()[0])
            self.assertTrue(all(row[0] for row in db.execute("SELECT discarded_at FROM roam_jobs WHERE job_id IN (?,?,?,?)",
                            (queued["id"], running["id"], accepted["id"], unknown["id"]))))

    def test_reference_uses_latest_valid_selected_task_then_cursor_actual_text(self):
        _, current = self.job(self.original["epoch"], completed=True)
        self.repo.roam_view({"artifact_id": current["id"], "viewed_at": 1})
        scoped = self.settings.save_options(prompt_mode="stay")
        reference = self.repo.roam_prompt_reference(scoped["epoch"], None)
        self.assertEqual(reference["positive"], current["positive"])
        self.assertEqual(reference["negative"], "blurry")
        selected = self.job(scoped["epoch"])
        self.job(scoped["epoch"], "failed")
        self.job(scoped["epoch"], "cancelled")
        discarded = self.job(scoped["epoch"], "running")
        with self.repo.connection() as db:
            db.execute("UPDATE roam_jobs SET discarded_at='discarded' WHERE job_id=?", (discarded["id"],))
        reference = Repository(self.paths.database).roam_prompt_reference(scoped["epoch"], current["id"])
        self.assertEqual(reference["positive"], selected["positive"])
        self.assertEqual(reference["candidate_id"], "candidate-2")
        self.assertEqual(reference["terms"], [{"text": "garden 2", "channel": "positive"}])
        self.assertIsNone(self.repo.roam_prompt_reference("unused-epoch", "missing-artifact"))

    def test_options_preserve_fields_and_failed_save_rolls_back_prefetch(self):
        _, image = self.job(self.original["epoch"], completed=True)
        preserved = self.settings.save_options(playback_interval=12)
        self.assertEqual(preserved["epoch"], self.original["epoch"])
        self.assertEqual(len(self.repo.artifacts(source="roam")), 1)
        saved = self.settings.save(7, "local", "preset", 30)
        self.assertNotEqual(saved["epoch"], preserved["epoch"])
        self.assertEqual(saved["playback_interval_seconds"], 12)
        self.assertEqual(len(self.repo.artifacts(source="roam")), 1)
        for mode in ("sequence", "", 1, [], {}):
            with self.subTest(mode=mode), self.assertRaises(ValidationError):
                self.settings.save_options(prompt_mode=mode)
        with self.repo.connection() as db:
            db.execute("CREATE TRIGGER reject_settings BEFORE UPDATE ON roam_settings BEGIN SELECT RAISE(ABORT,'reject'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.settings.save_options(liked_tags_only=True, prompt_mode="stay")
        self.assertEqual(self.settings.get(), saved)
        self.assertIsNone(self.repo.artifact(image["id"])["roam_hidden_at"])
        with self.repo.connection() as db:
            db.execute("DROP TRIGGER reject_settings")
        changed = self.settings.save_options(liked_tags_only=True, prompt_mode="stay")
        self.assertEqual(len(self.repo.artifacts(source="roam")), 0)  # No cursor: all prefetch invalidated.
        self.assertEqual(changed["prefetch_count"], 7)
        self.assertEqual(changed["playback_interval_seconds"], 12)
        self.assertEqual(RoamSettings(self.paths).get(), changed)
        unchanged = self.settings.save_options(liked_tags_only=True, prompt_mode="stay")
        self.assertEqual(unchanged["epoch"], changed["epoch"])


if __name__ == "__main__":
    unittest.main()
