"""Small persistence and numerical smoke coverage for image score reuse."""
from pathlib import Path
import tempfile
import unittest

from backend.contracts.recommendation import FeedbackUpdate, ScoreRequest
from backend.recommand import RecommendationService
from backend.store.recommendation import SQLiteRecommendationStore
from backend.store.sqlite import Repository, encode
from test_recommendation_core import MemoryStore, FakeEncoder, candidate


class ImageScoreCacheSmoke(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'data' / 'tmp'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'pictide.sqlite3'
        self.repo = Repository(self.path)
        self.recommendation = SQLiteRecommendationStore(self.repo)
        self.repo.save_backend(dict(id='local', kind='comfyui', bindings={}, workflow={}))
        self.sequence = 0

    def job(self, snapshot=None, count=1):
        self.sequence += 1
        job = self.repo.create_job(dict(request_id=f'cache-{self.sequence}', backend_id='local',
                                       positive='forest', negative='', seed=1))
        if snapshot is not None:
            with self.repo.connection() as db:
                db.execute('INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)',
                           (job['id'], 'epoch', encode(snapshot), '2026-10-18'))
        self.repo.complete(job['id'], [dict(node_id='9', index=i, filename=f'image-{i}.png')
                                       for i in range(count)])
        return [item['id'] for item in self.repo.artifacts() if item['job_id'] == job['id']]

    @staticmethod
    def record(identifier, score=.3):
        return dict(artifact_id=identifier, score=score, feature_version='features',
                    policy_version='policy', state_revision=4)

    def cache(self, ids=()):
        return self.repo.image_score_cache(ids, 'features', 'policy')

    def test_persistent_versioned_cache_and_only_manual_refresh_time(self):
        image = self.job()[0]
        self.recommendation.observe_score_range('local', 'features', 'policy', -.2, .8)
        self.repo.save_image_scores([self.record(image)], 0)
        self.assertEqual(self.cache([image])['scores'][image]['score'], .3)
        self.assertIsNone(self.cache()['refreshed_at'])
        stamp = '2026-10-18T12:00:00+00:00'
        self.repo.save_image_scores([self.record(image, .4)], 0, stamp)
        self.repo.save_image_scores([self.record(image, .5)], 0)
        reopened = Repository(self.path).image_score_cache([image], 'features', 'policy')
        self.assertEqual(reopened['scores'][image]['score'], .5)
        self.assertEqual(reopened['refreshed_at'], stamp)
        self.assertEqual(self.cache()['refreshed_at'], stamp, 'Refresh time is global, not limited to requested IDs')
        self.assertEqual((reopened['score_min'], reopened['score_max']), (-.2, .8))
        other = self.repo.image_score_cache([image], 'other-features', 'policy')
        self.assertEqual(other, dict(scores={}, score_min=None, score_max=None, refreshed_at=None))

    def test_reset_clears_cache_rejects_late_scores_and_retry_preserves_new_cache(self):
        image = self.job()[0]
        self.repo.save_image_scores([self.record(image)], 0, 'old-time')
        self.recommendation.reset_user('local', 'reset-once', 0)
        self.assertEqual(self.cache()['scores'], {})
        self.assertIsNone(self.cache()['refreshed_at'])
        self.repo.save_image_scores([self.record(image)], 0)
        self.assertEqual(self.cache([image])['scores'], {})
        self.repo.save_image_scores([self.record(image, .9)], 1, 'new-time')
        self.recommendation.reset_user('local', 'reset-once', 0)
        self.assertEqual(self.cache([image])['scores'][image]['score'], .9)
        self.assertEqual(self.cache()['refreshed_at'], 'new-time')

    def test_completion_records_same_mean_for_all_outputs_and_skips_old_reset(self):
        snapshot = dict(mean_score=.25, score=99., feature_version='features', policy_version='policy',
                        state_revision=7, score_reset_revision=0)
        images = self.job(snapshot, 2)
        scores = self.cache(images)['scores']
        self.assertEqual(len(scores), 2)
        self.assertTrue(all(item['score'] == .25 and item['state_revision'] == 7 for item in scores.values()))
        self.assertIsNone(self.cache()['refreshed_at'])
        old = self.job(dict(score=99.))[0]
        self.assertEqual(self.cache([old])['scores'], {})
        self.recommendation.reset_user('local', 'reset', 0)
        late = self.job(snapshot)[0]
        self.assertEqual(self.cache([late])['scores'], {})
        current = self.job(dict(snapshot, score_reset_revision=1))[0]
        self.assertEqual(self.cache([current])['scores'][current]['score'], .25)

    def test_thompson_returns_mean_without_changing_exploration_score(self):
        store = MemoryStore()
        service = RecommendationService(store, FakeEncoder())
        version = service.status().feature_version
        item = candidate()
        service.apply_feedback(FeedbackUpdate('local', 'liked', 1, 1, item, version))
        mean = service.score(ScoreRequest('mean', 'local', 5, (item,), 'mean')).scores[0]
        sampled = service.score(ScoreRequest('sampled', 'local', 5, (item,))).scores[0]
        self.assertEqual(mean.mean_score, mean.score)
        self.assertAlmostEqual(sampled.mean_score, mean.score)
        self.assertNotAlmostEqual(sampled.score, sampled.mean_score)


if __name__ == '__main__':
    unittest.main()