"""Shared posterior reuse without changing sampling, feedback or read-only views."""
import gc
import unittest
import weakref
from unittest.mock import patch

import numpy as np

from backend.recommendation import policy
from backend.recommendation.contracts import FeedbackUpdate, ScoreRequest
from backend.recommendation.features import dense_features
from backend.recommendation.service import RecommendationService
from tests.backend.recommendation.test_recommendation_core import FakeEncoder, candidate
from tests.backend.recommendation.test_recommendation_mean import ResetMemoryStore


class PosteriorCacheTests(unittest.TestCase):
    def setUp(self):
        self.store = ResetMemoryStore()
        self.encoder = FakeEncoder()
        self.service = RecommendationService(self.store, self.encoder)
        self.version = self.service.status().feature_version
        self.image = candidate(positive=("forest", "standing"), negative=("blurry",))

    def learn(self, value=1, revision=1):
        return self.service.apply_feedback(FeedbackUpdate("local", "image", revision, value, self.image, self.version))

    def score(self, items=None, seed=12, strategy="thompson", user="local"):
        return self.service.score(ScoreRequest("request", user, seed, tuple(items or [self.image]), strategy))

    def test_learning_warms_all_readers_without_blob_reads_or_deterministic_recomputation(self):
        self.learn()
        with patch.object(self.store, "load_policy", side_effect=AssertionError("Read state buffers")), \
             patch.object(np.linalg, "cholesky", side_effect=AssertionError("Repeated decomposition")), \
             patch.object(policy, "_posterior_mean", side_effect=AssertionError("Repeated mean solve")):
            first = self.score(seed=12)
            second = self.score(seed=13)
            repeated = self.score(seed=12)
            mean = self.score(strategy="mean")
            view = self.service.preferences("local")
        self.assertEqual(first.scores, repeated.scores)
        self.assertNotEqual(first.scores[0].score, second.scores[0].score, "Exploration must still draw fresh parameters")
        self.assertEqual(mean.scores[0].score, first.scores[0].mean_score)
        self.assertTrue(view.available)
        self.assertEqual((view.state_revision, view.evidence_count), (1, 1))

    def test_restart_loads_and_factors_once_across_scoring_and_preference_pages(self):
        self.learn()
        self.service = RecommendationService(self.store, self.encoder)
        with patch.object(self.store, "load_policy", wraps=self.store.load_policy) as reads, \
             patch.object(np.linalg, "cholesky", wraps=np.linalg.cholesky) as factors, \
             patch.object(policy, "_posterior_mean", wraps=policy._posterior_mean) as means:
            self.score()
            self.score(strategy="mean")
            self.service.preferences("local")
            self.score([candidate(positive=("new tag",))])
        self.assertEqual((reads.call_count, factors.call_count, means.call_count), (1, 1, 1))

    def test_varying_unseen_axes_match_full_matrix_sampling_without_expanding_cached_factor(self):
        self.learn()
        record = self.store.load_policy("local", self.version)
        populations = [
            [self.image, candidate("new", ("new one",), ("new negative",))],
            [candidate("repeat", ("forest", "forest", "other")), candidate("known", ("standing",))],
            [candidate("different", ("another", "new one"), ("forest",))],
        ]
        references = []
        for seed, items in enumerate(populations):
            prepared = self.service.features.prepare(items)
            keys, precision, reward = policy.unpack(record, {key for _, exact in prepared for key in exact})
            center, parameters = policy.scoring_parameters(precision, reward, seed)
            vectors = dense_features(prepared, keys)
            references.append((vectors @ center, vectors @ parameters))
        cached = self.service._posterior_cache
        with patch.object(np.linalg, "cholesky", side_effect=AssertionError("New tags triggered decomposition")), \
             patch.object(self.store, "load_policy", side_effect=AssertionError("New tags triggered state read")):
            for seed, (items, (means, values)) in enumerate(zip(populations, references)):
                result = self.score(items, seed)
                np.testing.assert_allclose([row.mean_score for row in result.scores], means, atol=1e-12)
                np.testing.assert_allclose([row.score for row in result.scores], values, atol=1e-12)
        self.assertIs(self.service._posterior_cache, cached)
        self.assertEqual(self.store.load_policy("local", self.version), record)

    def test_each_feedback_revision_factors_once_and_next_score_reuses_it(self):
        with patch.object(np.linalg, "cholesky", wraps=np.linalg.cholesky) as factors:
            for revision, value in enumerate((1, -1, None, 1), 1):
                self.assertEqual(self.learn(value, revision).status, "applied")
                self.assertEqual(factors.call_count, revision)
                self.score()
                self.score(strategy="mean")
                self.service.preferences("local")
                self.assertEqual(factors.call_count, revision)
        self.assertEqual(self.store.load_policy("local", self.version).evidence_count, 1)

    def test_failed_commit_never_publishes_uncommitted_posterior(self):
        self.learn()
        before = self.score(strategy="mean")
        cached = self.service._posterior_cache
        with patch.object(self.store, "commit_feedback", return_value=False):
            self.assertEqual(self.learn(-1, 2).status, "pending")
        self.assertIs(self.service._posterior_cache, cached)
        self.assertEqual(self.score(strategy="mean"), before)
        self.assertEqual(self.learn(-1, 2).status, "applied")
        self.assertAlmostEqual(self.score(strategy="mean").scores[0].score, -before.scores[0].score)

    def test_external_feedback_refreshes_cached_revision(self):
        self.learn()
        before = self.score(strategy="mean").scores[0].score
        other = RecommendationService(self.store, self.encoder)
        other.apply_feedback(FeedbackUpdate("local", "image", 2, -1, self.image, self.version))
        with patch.object(self.store, "load_policy", wraps=self.store.load_policy) as reads, \
             patch.object(np.linalg, "cholesky", wraps=np.linalg.cholesky) as factors:
            after = self.score(strategy="mean")
            self.score()
        self.assertEqual((reads.call_count, factors.call_count), (1, 1))
        self.assertEqual(after.state_revision, 2)
        self.assertAlmostEqual(after.scores[0].score, -before)

    def test_only_current_user_and_feature_version_remain_cached(self):
        self.learn()
        expected = self.score(strategy="mean").scores
        previous_factor = weakref.ref(self.service._posterior_cache.factor)
        self.assertEqual(self.score(strategy="mean", user="other").scores[0].score, 0.)
        gc.collect()
        self.assertIsNone(previous_factor(), "The previous large factor must be released")
        self.assertEqual(self.score(strategy="mean").scores, expected)
        self.encoder.version = "another-encoder"
        self.assertEqual(self.score(strategy="mean").scores[0].score, 0.)

    def test_recovered_scoring_does_not_make_a_missing_policy_look_persisted(self):
        self.learn()
        self.store.states.clear()
        result = self.score(strategy="mean")
        self.assertGreater(result.scores[0].score, 0.)
        self.assertFalse(self.service.preferences("local").available)
        self.assertEqual(self.store.states, {})
        self.assertEqual(self.learn(None, 2).status, "applied")
        self.assertTrue(self.service.preferences("local").available)


if __name__ == "__main__":
    unittest.main()
