from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from backend.store.sqlite import Repository
from tests.backend.roam.test_roam_cleanup import RoamCleanupFixture


class UnlikeGraceTests(RoamCleanupFixture, unittest.TestCase):
    def test_withdrawal_survives_restart_and_expires_after_24_hours(self):
        identifier, image, _ = self.artifact(self.old())
        self.repo.rate(identifier, 1)
        start = datetime.now(timezone.utc)
        with patch('backend.store.sqlite.now', return_value=start.isoformat()):
            self.repo.rate(identifier, None)
        self.repo = Repository(self.paths.database)
        for hours in (0, 23):
            with patch('backend.store.sqlite.now', return_value=(start + timedelta(hours=hours)).isoformat()):
                self.assertEqual(self.repo.expire_artifacts(start.isoformat()), 0)
        self.assertTrue(image.exists())
        with patch('backend.store.sqlite.now', return_value=(start + timedelta(hours=24)).isoformat()):
            self.assertEqual(self.repo.expire_artifacts(start.isoformat()), 1)

    def test_repeated_withdrawal_does_not_extend_the_grace_period(self):
        identifier, _, _ = self.artifact(self.old())
        self.repo.rate(identifier, 1)
        self.repo.rate(identifier, -1)
        with self.repo.connection() as db:
            deadline = db.execute('SELECT unliked_protected_until FROM artifacts WHERE id=?', (identifier,)).fetchone()[0]
        later = (datetime.fromisoformat(deadline) + timedelta(hours=1)).isoformat()
        with patch('backend.store.sqlite.now', return_value=later):
            self.repo.rate(identifier, None)
            self.assertEqual(self.repo.expire_artifacts(later), 1)

    def test_count_cleanup_skips_a_recently_unliked_image(self):
        protected, _, _ = self.roam_artifact(self.old())
        ordinary, _, _ = self.roam_artifact(self.old())
        anchor, _, _ = self.roam_artifact()
        self.view(anchor)
        self.repo.rate(protected, 1)
        self.repo.rate(protected, None)
        self.assertEqual(self.repo.trim_roam_artifacts(1), 1)
        self.assertIsNotNone(self.repo.artifact(protected))
        self.assertIsNone(self.repo.artifact(ordinary))


if __name__ == '__main__':
    unittest.main()
