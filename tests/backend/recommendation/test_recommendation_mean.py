"""Mean scoring reuses a posterior snapshot and bounds feature preparation."""
import unittest
from unittest.mock import patch

import numpy as np

from backend.recommendation.contracts import FeedbackUpdate, ResetResult, ResetState, ScoreRequest
from backend.recommendation.service import RecommendationService
from backend.recommendation import policy
from backend.recommendation.features import SEMANTIC_DIMENSION, content_key, dense_features
from tests.backend.recommendation.test_recommendation_core import MemoryStore, FakeEncoder, candidate


class ResetMemoryStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.reset = ResetState()

    def get_reset_state(self, user_id):
        return self.reset

    def reset_user(self, user_id, request_id, expected_reset_revision):
        self.states.clear()
        self.evidence.clear()
        self.reset = ResetState(self.reset.revision + 1, 0, "now")
        return ResetResult(request_id, self.reset.revision, "now")


class MeanScoringSmokeTests(unittest.TestCase):
    def setUp(self):
        self.store = ResetMemoryStore()
        self.encoder = FakeEncoder()
        self.service = RecommendationService(self.store, self.encoder)
        self.version = self.service.status().feature_version

    def learn(self, value=1, revision=1):
        return self.service.apply_feedback(FeedbackUpdate("local", "image", revision, value,
            candidate(positive=("forest", "forest", "standing"), negative=("blurry",)), self.version))

    def score(self, candidates):
        return self.service.score(ScoreRequest("mean", "local", 12, tuple(candidates), "mean"))

    def test_cached_bounded_sparse_scores_match_dense_with_unlearned_tags(self):
        self.learn()
        candidates = [candidate(str(i), ("forest", f"new {i}", "forest"), ("blurry", "new negative"))
                      for i in range(257)]
        prepared = self.service.features.prepare(candidates)
        extras = {key for _, exact in prepared for key in exact}
        record = self.store.load_policy("local", self.version)
        keys, precision, reward = policy.unpack(record, extras)
        center = policy.mean(precision, reward)
        expected = dense_features(prepared, keys) @ center
        self.assertEqual(center[SEMANTIC_DIMENSION + keys.index(content_key("new 0", "positive"))], 0.)
        with patch.object(policy, "mean", wraps=policy.mean) as solve, \
             patch.object(self.service.features, "prepare", wraps=self.service.features.prepare) as prepare, \
             patch.object(self.store, "observe_score_range", wraps=self.store.observe_score_range) as ranges:
            first = self.score(candidates)
            second = self.score(candidates)
        self.assertEqual(solve.call_count, 1)
        self.assertEqual([len(call.args[0]) for call in prepare.call_args_list], [128, 128, 1] * 2)
        self.assertEqual(ranges.call_count, 2, "Observe only once per complete request")
        np.testing.assert_allclose([item.score for item in first.scores], expected, atol=1e-12)
        self.assertEqual(first, second)

    def test_learning_reset_and_encoder_version_refresh_cached_mean(self):
        self.learn()
        image = candidate()
        with patch.object(policy, "mean", wraps=policy.mean) as solve:
            positive = self.score([image]).scores[0].score
            self.learn(-1, revision=2)
            negative = self.score([image]).scores[0].score
            self.assertAlmostEqual(positive, -negative)
            self.assertEqual(solve.call_count, 2)
            self.service.reset_preferences("local", "reset", 0)
            self.assertIsNone(self.service._mean_cache)
            self.assertEqual(self.score([image]).scores[0].score, 0.)
            self.learn()
            self.score([image])
            self.assertEqual(solve.call_count, 3)
            self.encoder.version = "another-encoder"
            self.assertEqual(self.score([image]).scores[0].score, 0.)
            self.assertEqual(solve.call_count, 3, "Cold-start mean needs no matrix solve")

    def test_external_reset_with_reused_state_revision_cannot_reuse_mean(self):
        self.learn()
        first = self.score([candidate()]).scores[0].score
        self.store.reset_user("local", "external", 0)
        other = RecommendationService(self.store, self.encoder)
        other.apply_feedback(FeedbackUpdate("local", "new", 1, -1,
            candidate(positive=("forest", "forest", "standing"), negative=("blurry",)), self.version))
        with patch.object(policy, "mean", wraps=policy.mean) as solve:
            second = self.score([candidate()]).scores[0].score
        self.assertEqual(solve.call_count, 1)
        self.assertAlmostEqual(first, -second)


if __name__ == "__main__":
    unittest.main()