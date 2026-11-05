from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from backend.store.sqlite import Repository
from backend.domain import ValidationError
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

    def test_recent_unlikes_include_hidden_sources_and_exclude_other_states(self):
        start = datetime.now(timezone.utc)
        generated = self.artifact(self.old())[0]
        roam = self.roam_artifact()[0]
        restored = self.artifact()[0]
        deleted = self.artifact()[0]
        expired = self.artifact()[0]
        self.artifact()  # Never liked.
        for identifier in (generated, roam, restored, deleted, expired):
            self.repo.rate(identifier, 1)
        self.repo.clear_generated(generated)
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET roam_hidden_at=? WHERE id=?", (start.isoformat(), roam))
        with patch('backend.store.sqlite.now', return_value=(start - timedelta(hours=25)).isoformat()):
            self.repo.rate(expired, None)
        with patch('backend.store.sqlite.now', return_value=start.isoformat()):
            for identifier in (generated, restored, deleted):
                self.repo.rate(identifier, None)
        self.repo.rate(restored, 1)
        self.repo.clear_generated(deleted)
        later = (start + timedelta(minutes=1)).isoformat()
        with patch('backend.store.sqlite.now', return_value=later):
            self.repo.rate(roam, -1)
            self.repo = Repository(self.paths.database)
            page = self.repo.recent_unlikes_page()
        self.assertEqual([row['id'] for row in page['artifacts']], [roam, generated])
        self.assertEqual([row['feedback'] for row in page['artifacts']], [-1, None])
        self.assertEqual([row['source'] for row in page['artifacts']], ['roam', 'generate'])
        self.assertEqual(page['total'], 2)
        self.assertEqual(page['server_time'], later)
        self.assertFalse(page['has_more'])

    def test_recent_cursor_survives_restoring_and_moving_its_boundary(self):
        identifiers = [self.artifact()[0] for _ in range(5)]
        start = datetime.now(timezone.utc)
        with patch('backend.store.sqlite.now', return_value=start.isoformat()):
            for identifier in identifiers:
                self.repo.rate(identifier, 1)
                self.repo.rate(identifier, None)
            first = self.repo.recent_unlikes_page(2)
        self.assertEqual([row['id'] for row in first['artifacts']], sorted(identifiers, reverse=True)[:2])
        boundary = first['artifacts'][-1]['id']
        self.repo.rate(boundary, 1)
        second = self.repo.recent_unlikes_page(2, first['next_cursor'])
        self.assertEqual([row['id'] for row in second['artifacts']], sorted(identifiers, reverse=True)[2:4])
        self.repo.rate(boundary, None)
        second_again = self.repo.recent_unlikes_page(2, first['next_cursor'])
        self.assertEqual(second_again['artifacts'], second['artifacts'])
        last = self.repo.recent_unlikes_page(2, second['next_cursor'])
        self.assertEqual([row['id'] for row in last['artifacts']], sorted(identifiers, reverse=True)[4:])
        self.assertFalse(last['has_more'])
        self.assertIsNone(last['next_cursor'])

    def test_recent_list_ends_at_deadline_without_claiming_the_file_was_deleted(self):
        identifier, image, _ = self.artifact()
        self.repo.rate(identifier, 1)
        artifact = self.repo.rate(identifier, None)
        deadline = artifact['unliked_protected_until']
        with patch('backend.store.sqlite.now', return_value=(datetime.fromisoformat(deadline) - timedelta(microseconds=1)).isoformat()):
            self.assertEqual(self.repo.recent_unlikes_page()['total'], 1)
        with patch('backend.store.sqlite.now', return_value=deadline):
            self.assertEqual(self.repo.recent_unlikes_page()['artifacts'], [])
        self.assertTrue(image.exists())
        self.assertIsNotNone(self.repo.artifact(identifier))

    def test_recent_list_rejects_invalid_limits_and_cursors(self):
        for limit in (0, 201, True, '1'):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                self.repo.recent_unlikes_page(limit)
        for cursor in ('', 'invalid', '{}', '[1,2]', '["yesterday","id"]', 'x' * 257):
            with self.subTest(cursor=cursor), self.assertRaises(ValidationError):
                self.repo.recent_unlikes_page(before=cursor)


if __name__ == '__main__':
    unittest.main()
