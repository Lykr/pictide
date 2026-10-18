"""Preference-score smoke: deterministic ranges, HTTP display semantics and reset."""
import unittest
from unittest.mock import patch
from backend.contracts.recommendation import FeedbackUpdate, ScoreRequest
from backend.recommand import RecommendationService
from backend.recommand import policy
from test_recommendation_core import MemoryStore, FakeEncoder, candidate
from test_recommendation_application import RecommendationApplicationTests


class ScoreRangeSmoke(unittest.TestCase):
    def test_range_uses_all_posterior_means_not_exploration(self):
        service = RecommendationService(MemoryStore(), FakeEncoder())
        version = service.status().feature_version
        a, b = candidate('forest', ('forest',)), candidate('city', ('city',))
        cold = service.score(ScoreRequest('cold', 'local', 1, (a, b)))
        self.assertEqual((cold.score_min, cold.score_max), (0, 0))
        self.assertTrue(any(item.score != 0 for item in cold.scores))
        service.apply_feedback(FeedbackUpdate('local', 'a', 1, 1, a, version))
        service.apply_feedback(FeedbackUpdate('local', 'b', 2, -1, b, version))
        mean = service.score(ScoreRequest('mean', 'local', 2, (a, b), 'mean'))
        self.assertAlmostEqual(mean.score_min, min(item.score for item in mean.scores))
        self.assertAlmostEqual(mean.score_max, max(item.score for item in mean.scores))
        sampled = service.score(ScoreRequest('sample', 'local', 8, (a, b)))
        self.assertEqual((sampled.score_min, sampled.score_max), (mean.score_min, mean.score_max))
        self.assertNotEqual(sampled.scores, mean.scores)
        # A smaller later request cannot shrink the global observed range.
        narrowed = service.score(ScoreRequest('narrow', 'local', 9, (a,), 'mean'))
        self.assertEqual((narrowed.score_min, narrowed.score_max), (mean.score_min, mean.score_max))
        other = service.score(ScoreRequest('other-user', 'other', 1, (a,), 'mean'))
        self.assertEqual((other.score_min, other.score_max), (0, 0))


class ImageScoreSmoke(RecommendationApplicationTests):
    async def test_image_score_snapshot_mean_range_and_reset(self):
        image = self.output(1)[0]
        path = f"/api/artifacts/{image['id']}/preference-score"
        response = await self.client.get(path)
        self.assertEqual(response.status, 200)
        cold = await response.json()
        self.assertEqual(cold['status'], 'scored')
        self.assertIsNone(cold['love_score'])
        self.assertEqual((cold['score_min'], cold['score_max']), (0, 0))
        await self.rate(image, 1)
        revision = self.policy().revision
        response = await self.client.get(path)
        scored = await response.json()
        self.assertGreater(scored['score'], 0)
        self.assertEqual(scored['love_score'], 100)
        self.assertEqual(scored['state_revision'], revision)
        self.assertEqual(await (await self.client.get(path)).json(), scored)
        self.assertEqual(self.policy().revision, revision, 'Viewing must not learn')
        with self.app.storage.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM recommendation_score_range').fetchone()[0], 1)
        with patch.object(self.app.recommendation.encoder, 'available', return_value=False):
            unavailable = await (await self.client.get(path)).json()
            self.assertEqual(unavailable['status'], 'unavailable')
            self.assertIsNone(unavailable['love_score'])
        self.assertEqual((await self.client.get('/api/artifacts/nonexistent/preference-score')).status, 404)
        manual = self.app.storage.create_job(dict(backend_id='local',request_id='manual-score',positive='forest',negative='',seed=42))
        self.app.storage.complete(manual['id'], [dict(node_id='9',index=0,filename='manual.png')])
        generated = self.app.storage.artifacts(source='generate')[0]
        missing = await (await self.client.get(f"/api/artifacts/{generated['id']}/preference-score")).json()
        self.assertEqual(missing['status'], 'missing_snapshot')
        reset = await self.client.post('/api/recommendation/preferences/reset', json=dict(request_id='score-reset',expected_reset_revision=0))
        self.assertEqual(reset.status, 200)
        with self.app.storage.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM recommendation_score_range').fetchone()[0], 0)
        after = await (await self.client.get(path)).json()
        self.assertEqual((after['score_min'],after['score_max']), (0,0))
        self.assertIsNone(after['love_score'])
        self.assertEqual(self.app.storage.artifact(image['id'])['feedback'], 1)