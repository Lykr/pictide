"""User preference reset boundaries, idempotency, isolation and rollback."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest
import uuid

from backend.contracts.recommendation import PolicyRecord, ResetState, ScoreCandidate, ScoreTerm
from backend.domain import ConflictError
from backend.store.recommendation import SQLiteRecommendationStore
from backend.store.sqlite import Repository


class PreferenceResetStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Repository(Path(self.temp.name) / 'pictide.sqlite3')
        self.store = SQLiteRecommendationStore(self.repo)
        self.repo.save_backend({'id': 'local', 'kind': 'comfyui', 'bindings': {}, 'workflow': {}})
        self.candidate = ScoreCandidate('combo', 'forest', 'blurry',
                                        (ScoreTerm('forest'), ScoreTerm('blurry', 'negative')))

    def image(self):
        job = self.repo.create_job({'request_id': str(uuid.uuid4()), 'backend_id': 'local',
                                    'positive': 'forest', 'negative': 'blurry', 'seed': 1})
        self.repo.complete(job['id'], [{'node_id': '9', 'index': 0, 'filename': 'image.png'}])
        with self.repo.connection() as db:
            db.execute('INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)',
                       (job['id'], 'epoch', json.dumps(asdict(self.candidate)), '2026-01-01'))
        return next(a['id'] for a in self.repo.artifacts() if a['job_id'] == job['id'])

    @staticmethod
    def state(revision, count=1):
        return PolicyRecord(revision, ('positive:forest',), struct.pack('<4d', 1, 0, 0, 1),
                            struct.pack('<2d', 1, 2), count)

    def learn(self, image_id, version='v1', user='local'):
        if user == 'local':
            self.repo.rate(image_id, 1)
        else:
            from backend.store.recommendation import record_feedback
            with self.repo.connection() as db:
                db.execute('INSERT INTO feedback VALUES (?,?,1,?)', (image_id, user, '2026-01-01'))
                record_feedback(db, image_id, user, 1)
        update = next(u for u in self.store.pending_feedback(user, version) if u.artifact_id == image_id)
        previous = self.store.load_policy(user, version)
        expected = previous.revision if previous else 0
        self.assertTrue(self.store.commit_feedback(update, self.state(expected + 1), expected))
        return update

    def test_default_and_empty_reset_persist_without_learning(self):
        self.assertEqual(self.store.get_reset_state('local'), ResetState())
        result = self.store.reset_user('local', 'reset-empty', 0)
        self.assertEqual(result.reset_revision, 1)
        self.assertIsNotNone(datetime.fromisoformat(result.reset_at).tzinfo)
        restart = SQLiteRecommendationStore(Repository(self.repo.path))
        self.assertEqual(restart.get_reset_state('local'), ResetState(1, 0, result.reset_at))
        self.assertEqual(restart.reset_user('local', 'reset-empty', 0), result)

    def test_preserves_likes_images_events_jobs_and_cache(self):
        iid = self.image()
        update = self.learn(iid)
        self.store.save_vectors('encoder', {'forest': (0.1, 0.5)})
        with self.repo.connection() as db:
            before = {table: db.execute(f'SELECT * FROM {table}').fetchall()
                      for table in ('artifacts', 'jobs', 'feedback', 'roam_jobs', 'recommendation_events',
                                    'recommendation_vectors')}
        result = self.store.reset_user('local', 'reset-preserve', 0)
        self.assertEqual(self.store.get_reset_state('local'), ResetState(1, update.revision, result.reset_at))
        self.assertIsNone(self.store.load_policy('local', 'v1'))
        self.assertEqual(self.store.load_evidence('local', 'v1'), ())
        self.assertEqual(self.repo.artifact(iid)['feedback'], 1)
        with self.repo.connection() as db:
            for table, rows in before.items():
                self.assertEqual(db.execute(f'SELECT * FROM {table}').fetchall(), rows, table)
        self.assertAlmostEqual(self.store.load_vectors('encoder', ['forest'])['forest'][0], 0.1)

    def test_pending_failed_old_feedback_filtered_after_restart_all_versions(self):
        iid = self.image()
        self.repo.rate(iid, 1)
        old = self.store.pending_feedback('local', 'v1')[0]
        self.store.reset_user('local', 'reset-unapplied', 0)
        restart = SQLiteRecommendationStore(Repository(self.repo.path))
        self.assertEqual(restart.get_reset_state('local').event_floor, old.revision)
        for version in ('v1', 'v2'):
            restart.seed_feedback('local', version)
            self.assertEqual(restart.pending_feedback('local', version), ())

    def test_historical_seed_suppressed_even_without_any_prior_event(self):
        iid = self.image()
        with self.repo.connection() as db:
            db.execute("INSERT INTO feedback VALUES (?,'local',1,'2026-01-01')", (iid,))
        self.store.reset_user('local', 'reset-legacy', 0)
        self.store.seed_feedback('local', 'new-version')
        self.assertEqual(self.store.pending_feedback('local', 'new-version'), ())
        self.assertEqual(self.repo.artifact(iid)['feedback'], 1)

    def test_new_feedback_learns_and_unchanged_like_does_not_restore(self):
        old = self.image()
        old_update = self.learn(old)
        self.store.reset_user('local', 'reset-new', 0)
        self.repo.rate(old, 1)
        self.assertEqual(self.store.pending_feedback('local', 'v1'), ())
        new_update = self.learn(self.image())
        self.assertGreater(new_update.revision, old_update.revision)
        self.assertEqual(self.store.load_evidence('local', 'v1'), (new_update,))

    def test_retract_then_relike_is_new_evidence(self):
        iid = self.image()
        self.learn(iid)
        self.store.reset_user('local', 'reset-relike', 0)
        self.repo.rate(iid, None)
        retract = self.store.pending_feedback('local', 'v1')[0]
        self.assertIsNone(retract.value)
        self.assertTrue(self.store.commit_feedback(retract, self.state(1, 0), 0))
        relike = self.learn(iid)
        self.assertEqual(relike.value, 1)
        self.assertGreater(relike.revision, retract.revision)
        self.assertEqual(self.store.load_evidence('local', 'v1'), (relike,))

    def test_idempotent_retry_preserves_new_learning_and_reused_payload_conflicts(self):
        self.learn(self.image())
        result = self.store.reset_user('local', 'reset-once', 0)
        new = self.learn(self.image())
        self.assertEqual(self.store.reset_user('local', 'reset-once', 0), result)
        self.assertEqual(self.store.load_evidence('local', 'v1'), (new,))
        with self.assertRaises(ConflictError):
            self.store.reset_user('local', 'reset-once', 1)
        with self.assertRaises(ConflictError):
            self.store.reset_user('local', 'different-reset', 0)
        self.assertEqual(self.store.get_reset_state('local').revision, 1)
        self.assertEqual(self.store.load_evidence('local', 'v1'), (new,))
        self.store.reset_user('local', 'reset-twice', 1)
        self.assertIsNone(self.store.load_policy('local', 'v1'))
        self.assertEqual(self.store.reset_user('local', 'reset-once', 0), result)
        self.assertEqual(self.store.get_reset_state('local').revision, 2)

    def test_concurrent_distinct_reset_requests_compare_and_swap(self):
        self.learn(self.image())
        def reset(request_id):
            try:
                return self.store.reset_user('local', request_id, 0).reset_revision
            except ConflictError:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reset, ['reset-left', 'reset-right']))
        self.assertCountEqual(results, [1, 'conflict'])
        self.assertEqual(self.store.get_reset_state('local').revision, 1)

    def test_concurrent_same_request_returns_same_result(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.store.reset_user('local', 'reset-same', 0), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.store.get_reset_state('local').revision, 1)

    def test_old_inflight_commit_rejected_even_when_policy_cas_matches_zero(self):
        iid = self.image()
        self.repo.rate(iid, 1)
        old = self.store.pending_feedback('local', 'v1')[0]
        self.store.reset_user('local', 'reset-race', 0)
        self.assertFalse(self.store.commit_feedback(old, self.state(1), 0))
        self.assertFalse(self.store.commit_feedback(replace(old, feature_version='new-version'), self.state(1), 0))
        self.assertFalse(self.store.commit_feedback(replace(old, artifact_id='fabricated', revision=old.revision + 1),
                                                    self.state(1), 0))
        self.assertIsNone(self.store.load_policy('local', 'v1'))
        self.learn(self.image())
        self.assertFalse(self.store.commit_feedback(old, self.state(2), 1))

    def test_all_versions_cleared_other_users_and_new_version_replay_preserved(self):
        iid = self.image()
        self.learn(iid, 'v1')
        self.learn(iid, 'v2')
        other = self.learn(iid, 'v1', 'other')
        self.store.reset_user('local', 'reset-scope', 0)
        for version in ('v1', 'v2', 'v3'):
            self.assertIsNone(self.store.load_policy('local', version))
            self.assertEqual(self.store.load_evidence('local', version), ())
            self.assertEqual(self.store.pending_feedback('local', version), ())
        self.assertEqual(self.store.get_reset_state('other'), ResetState())
        self.assertEqual(self.store.load_evidence('other', 'v1'), (other,))
        self.assertEqual(len(self.store.pending_feedback('other', 'v2')), 1)
        new = self.learn(self.image())
        self.store.seed_feedback('local', 'v3')
        self.assertEqual(self.store.pending_feedback('local', 'v3'), (replace(new, feature_version='v3'),))

    def test_reset_transaction_rolls_back_deleted_state_watermark_and_request(self):
        update = self.learn(self.image())
        before = self.store.load_policy('local', 'v1')
        with self.repo.connection() as db:
            db.execute("CREATE TRIGGER fail_reset BEFORE INSERT ON recommendation_reset_requests "
                       "BEGIN SELECT RAISE(ABORT, 'simulated interruption'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.reset_user('local', 'reset-failure', 0)
        self.assertEqual(self.store.get_reset_state('local'), ResetState())
        self.assertEqual(self.store.load_policy('local', 'v1'), before)
        self.assertEqual(self.store.load_evidence('local', 'v1'), (update,))
        with self.repo.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM recommendation_reset_requests').fetchone()[0], 0)
            db.execute('DROP TRIGGER fail_reset')
        self.assertEqual(self.store.reset_user('local', 'reset-failure', 0).reset_revision, 1)


if __name__ == '__main__':
    unittest.main()
