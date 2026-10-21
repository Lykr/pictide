"""Two-job dispatch persistence smokes; isolated SQLite, no GPU requests."""
from pathlib import Path
import tempfile
import unittest

from backend.store.sqlite import Repository


class DispatchStoreSmoke(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Repository(Path(self.directory.name) / "pictide.sqlite3")
        self.repo.save_backend({"id": "local", "name": "Local", "bindings": {}})

    def create(self, request_id, roam=False):
        job = self.repo.create_job(dict(backend_id="local", request_id=request_id,
                                       positive="landscape", negative="", seed=1))
        if roam:
            with self.repo.connection() as db:
                db.execute("INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES(?,?,?,?)",
                           (job["id"], "smoke", "{}", job["created_at"]))
        return job

    def identifiers(self):
        return [job["id"] for job in self.repo.dispatch_jobs()]

    def test_window_manual_priority_and_cancelled_backend_occupancy(self):
        roam = self.create("old-roam", roam=True)
        first = self.create("manual-first")
        second = self.create("manual-second")
        self.assertEqual(self.identifiers(), [first["id"], second["id"]])
        self.assertTrue(self.repo.claim_job(first["id"]))
        self.assertFalse(self.repo.claim_job(first["id"]))
        self.repo.attach_prompt(first["id"], "accepted-first")
        self.repo.update_job(first["id"], "cancelled")
        # Cancellation alone cannot free an accepted prompt's window slot.
        self.assertEqual(self.identifiers(), [first["id"], second["id"]])
        self.assertTrue(self.repo.claim_job(second["id"]))
        self.assertEqual(self.identifiers(), [first["id"], second["id"]])
        self.repo.finish_dispatch(first["id"])
        self.assertEqual(self.repo.job(first["id"])["status"], "cancelled")
        self.assertEqual(self.identifiers(), [second["id"], roam["id"]])
        # A late POST response must retain occupancy even after cancellation.
        self.repo.attach_prompt(first["id"], "accepted-first")
        self.assertEqual(self.identifiers(), [first["id"], second["id"]])
        self.assertNotIn("backend_pending", self.repo.job(first["id"]))
        self.assertTrue(all("backend_pending" not in row for row in self.repo.jobs()))

    def test_recovery_keeps_uncertain_and_cancelled_pending_without_resubmit(self):
        uncertain = self.create("uncertain")
        self.repo.claim_job(uncertain["id"])
        cancelled = self.create("cancelled")
        self.repo.claim_job(cancelled["id"])
        self.repo.update_job(cancelled["id"], "cancelled")
        self.repo.attach_prompt(cancelled["id"], "external-cancelled")
        historical = self.create("historical-unknown")
        self.repo.update_job(historical["id"], "unknown")
        queued = self.create("queued")
        reopened = Repository(self.repo.path)
        reopened.recover_submissions()
        self.assertEqual(reopened.job(uncertain["id"])["status"], "unknown")
        self.assertEqual([row["id"] for row in reopened.dispatch_jobs()],
                         [uncertain["id"], cancelled["id"]])
        self.assertFalse(reopened.claim_job(uncertain["id"]))
        self.assertNotIn("backend_pending", reopened.unknown_jobs()[0])
        reopened.finish_dispatch(uncertain["id"])
        self.assertEqual([row["id"] for row in reopened.dispatch_jobs()],
                         [cancelled["id"], queued["id"]])

    def test_recovery_rechecks_interrupted_save_and_returns_all_accepted_work(self):
        accepted = [self.create(f"accepted-{n}") for n in range(3)]
        for job in accepted:
            self.repo.claim_job(job["id"])
            self.repo.attach_prompt(job["id"], "external-" + job["request_id"])
            self.repo.update_job(job["id"], "running")
        self.repo.finish_dispatch(accepted[0]["id"])
        self.create("still-queued")
        self.repo.recover_submissions()
        # More than the current cap may already exist on restart: inspect all,
        # then decline any new submission until enough slots become free.
        self.assertEqual(self.identifiers(), [job["id"] for job in accepted])
        self.assertTrue(all(row["backend_pending"] for row in self.repo.dispatch_jobs()))
        self.repo.finish_dispatch(accepted[0]["id"])
        self.repo.complete(accepted[0]["id"], [])
        self.repo.recover_submissions()
        self.assertEqual(self.identifiers(), [job["id"] for job in accepted[1:]])


if __name__ == "__main__":
    unittest.main()
