"""Count retention protects likes and other galleries through durable cleanup."""
import unittest
from backend.store.cleanup import LazyCleanup, delete_pending
from backend.store.sqlite import Repository
from test_cleanup import CleanupFixture


class RoamCleanupFixture(CleanupFixture):
    def roam_artifact(self, timestamp=None):
        identifier, image, job = self.artifact(timestamp)
        with self.repo.connection() as db:
            db.execute("INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)", (job["id"], "test", "{}", job["created_at"]))
        return identifier, image, job

    def view(self, identifier):
        self.view_clock = getattr(self, "view_clock", 0) + 1
        self.repo.roam_view({"artifact_id": identifier, "viewed_at": self.view_clock})


class RoamCountStorageTests(RoamCleanupFixture, unittest.TestCase):
    def test_all_old_history_counts_liked_are_hidden_and_unliked_files_are_removed(self):
        oldest = self.roam_artifact("2026-01-01T00:00:00Z")
        liked = self.roam_artifact("2025-01-01T00:00:00Z")
        newer = self.roam_artifact("2026-01-02T00:00:00Z")
        newest = self.roam_artifact("2026-01-03T00:00:00Z")
        manual = self.artifact("2024-01-01T00:00:00Z")
        # A like from any actor protects an artifact.
        with self.repo.connection() as db:
            db.execute("INSERT INTO feedback VALUES (?,'other',1,'2026-01-01')", (liked[0],))
        self.view(newest[0])
        revision = self.repo.artifact_revision()
        self.assertEqual(self.repo.trim_roam_artifacts(1), 2)
        self.assertEqual(self.repo.artifact_revision(), revision + 2)
        self.assertIsNone(self.repo.artifact(oldest[0]))
        for entry in (liked, newer, newest, manual):
            self.assertIsNotNone(self.repo.artifact(entry[0]))
        self.assertIsNotNone(self.repo.artifact(liked[0])["roam_hidden_at"])
        self.assertEqual({row["id"] for row in self.repo.artifacts(source="roam")}, {newer[0], newest[0]})
        self.assertEqual(self.repo.counts(), {"artifacts": 4, "roam": 2, "generate": 1, "liked": 0})
        self.assertEqual(delete_pending(self.repo, self.paths, 100), 1)
        self.assertFalse(oldest[1].exists())
        self.assertFalse(oldest[1].with_suffix('.json').exists())
        self.assertTrue(liked[1].exists())
        self.assertTrue(liked[1].with_suffix('.json').exists())
        self.assertEqual(self.repo.job(oldest[2]['id'])['status'], 'completed')
        self.assertIsNone(Repository(self.paths.database).artifact(oldest[0]))
        self.assertEqual(self.repo.trim_roam_artifacts(1), 0)

    def test_disabled_batch_bound_order_and_no_shared_file_loss(self):
        rows = [self.roam_artifact("2026-01-01T00:00:00Z") for _ in range(4)]
        ordered = sorted(rows, key=lambda row: row[0])
        self.view(ordered[-1][0])
        self.assertEqual(self.repo.trim_roam_artifacts(0), 0)
        self.assertEqual(self.repo.trim_roam_artifacts(1, 1), 1)
        self.assertIsNone(self.repo.artifact(ordered[0][0]))
        self.assertEqual(self.repo.trim_roam_artifacts(1), 1)
        self.assertIsNotNone(self.repo.artifact(ordered[-1][0]))
        # Shared files referenced by a surviving gallery item remain protected.
        with self.repo.connection() as db:
            db.execute("UPDATE artifacts SET local_path=? WHERE id=?", (ordered[0][1].relative_to(self.paths.root).as_posix(), ordered[-1][0]))
        delete_pending(self.repo, self.paths, 100)
        self.assertTrue(ordered[0][1].exists())
        self.assertTrue(ordered[0][1].with_suffix('.json').exists())

    def test_sort_uses_utc_time_not_timestamp_text(self):
        newer = self.roam_artifact("2026-01-01T01:00:00+00:00")
        older = self.roam_artifact("2026-01-01T02:00:00+02:00")
        current = self.roam_artifact("2026-01-02T00:00:00Z")
        self.view(current[0])
        self.assertEqual(self.repo.trim_roam_artifacts(1), 1)
        self.assertIsNone(self.repo.artifact(older[0]))
        self.assertIsNotNone(self.repo.artifact(newer[0]))

    def test_only_history_counts_current_future_and_missing_view_are_protected(self):
        rows = [self.roam_artifact(f"2026-01-0{index+1}T00:00:00Z") for index in range(5)]
        self.assertEqual(self.repo.trim_roam_artifacts(1), 0)
        self.view(rows[2][0])
        self.assertEqual(self.repo.trim_roam_artifacts(1), 1)
        self.assertIsNone(self.repo.artifact(rows[0][0]))
        for row in rows[1:]:
            self.assertIsNotNone(self.repo.artifact(row[0]))
        # Likes count as history; once hidden they never reappear in roam.
        self.repo.rate(rows[1][0], 1)
        self.view(rows[4][0])
        self.assertEqual(self.repo.trim_roam_artifacts(1), 2)
        self.assertIsNotNone(self.repo.artifact(rows[1][0])["roam_hidden_at"])
        self.repo.rate(rows[1][0], None)
        self.assertEqual(self.repo.trim_roam_artifacts(1), 0)
        self.assertNotIn(rows[1][0], {row["id"] for row in self.repo.artifacts(source="roam")})

    def test_hidden_likes_pagination_ready_counts_and_restart(self):
        rows = [self.roam_artifact(f"2026-01-0{index+1}T00:00:00Z") for index in range(5)]
        for row in rows[:3]:
            self.repo.rate(row[0], 1)
        self.view(rows[3][0])
        self.assertEqual(self.repo.trim_roam_artifacts(1), 2)
        self.assertEqual({row['id'] for row in self.repo.artifacts(liked=True)}, {row[0] for row in rows[:3]})
        self.assertEqual([row['id'] for row in self.repo.artifacts(source='roam')], [rows[4][0], rows[3][0], rows[2][0]])
        page = self.repo.artifact_page(source='roam', around=rows[0][0], limit=2)
        self.assertEqual(page['anchor_id'], rows[2][0])
        self.assertEqual(page['total'], 3)
        self.assertEqual(self.repo.ensure_roam('test', None, 0)['ready'], 3)
        self.assertEqual(self.repo.ensure_roam('test', rows[3][0], 0)['ready'], 1)
        reloaded = Repository(self.paths.database)
        self.assertEqual(reloaded.counts(), {"artifacts": 5, "roam": 3, "generate": 0, "liked": 3})
        self.assertEqual(len(reloaded.artifacts(liked=True)), 3)
        self.assertEqual(len(reloaded.artifacts(source='roam', before=rows[1][0])), 0)


class RoamLazyCleanupTests(RoamCleanupFixture, unittest.IsolatedAsyncioTestCase):
    async def test_count_limit_checks_new_images_inside_age_throttle_and_disabled_pending_retry(self):
        cap = [1]
        cleanup = LazyCleanup(self.repo, self.paths, lambda: 0, max_roam_history=lambda: cap[0])
        oldest = self.roam_artifact()
        self.roam_artifact()
        self.view(self.repo.artifacts(source='roam')[0]['id'])
        await cleanup.maybe_cleanup(force=True)
        latest = self.roam_artifact()
        self.view(latest[0])
        result = await cleanup.maybe_cleanup()
        self.assertEqual(result['roam_trimmed'], 1)
        self.assertIsNone(self.repo.artifact(oldest[0]))
        self.assertTrue(latest[1].exists())
        self.assertFalse(oldest[1].exists())
        cap[0] = 0
        extra = self.roam_artifact()
        await cleanup.maybe_cleanup(force=True)
        self.assertIsNotNone(self.repo.artifact(extra[0]))

    async def test_startup_enforces_saved_count_without_background_work(self):
        rows = [self.roam_artifact() for _ in range(3)]
        self.view(rows[-1][0])
        cleanup = LazyCleanup(self.repo, self.paths, lambda: 0, max_roam_history=lambda: 1)
        self.assertEqual((await cleanup.maybe_cleanup(force=True))['roam_trimmed'], 1)
        self.assertEqual(len(self.repo.artifacts(source='roam')), 2)
        self.assertEqual(sum(row[1].exists() for row in rows), 2)

    async def test_roam_only_save_skips_global_expiration_and_hidden_only_updates_revision(self):
        rows = [self.roam_artifact() for _ in range(3)]
        self.repo.rate(rows[0][0], 1)
        self.view(rows[2][0])
        manual = self.artifact('2000-01-01T00:00:00Z')
        cleanup = LazyCleanup(self.repo, self.paths, lambda: 1, max_roam_history=lambda: 1)
        stats = await cleanup.maybe_cleanup(force=True, roam_only=True)
        self.assertEqual(stats['expired'], 0)
        self.assertEqual(stats['deleted'], 0)
        self.assertEqual(stats['revision'], 1)
        self.assertIsNotNone(self.repo.artifact(manual[0]))
        self.assertTrue(manual[1].exists())
        self.assertTrue(rows[0][1].exists())
