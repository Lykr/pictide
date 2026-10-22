"""Posterior information gain, bounded scoring, and reversible exploration evidence."""
import unittest
from unittest.mock import patch

import numpy as np

from backend.recommendation import exploration, policy
from backend.recommendation.contracts import FeedbackUpdate, ScoreRequest
from backend.recommendation.features import content_key, dense_features
from backend.recommendation.service import RecommendationService
from tests.backend.recommendation.test_recommendation_core import FakeEncoder, candidate
from tests.backend.recommendation.test_recommendation_mean import ResetMemoryStore


A, B = content_key("forest", "positive"), content_key("standing", "positive")


class ContrastNumericalTests(unittest.TestCase):
    def test_analytic_gain_matches_an_actual_posterior_update(self):
        precision = np.eye(2) + np.ones((2, 2))
        vectors = np.array([[1., 0.], [0., 1.], [1., 1.]])
        prepared = [((), {key: value for key, value in zip((A, B), x) if value}) for x in vectors]
        observed = {A: frozenset(range(3)), B: frozenset(range(3))}
        with patch("numpy.linalg.inv", side_effect=AssertionError("No full inverse in scoring")):
            rewards = exploration.rewards(np.linalg.cholesky(precision), (A, B), prepared, vectors, observed)
        np.testing.assert_allclose(rewards, [.2, .2, 0.], atol=1e-12)
        d = np.array([1., -1.])
        before = d @ np.linalg.solve(precision, d)
        for x, expected in zip(vectors, (.6, .6, 0.)):
            after = d @ np.linalg.solve(precision + np.outer(x, x), d)
            self.assertAlmostEqual(before - after, expected)

    def test_normalized_full_features_match_dense_covariance_with_nuisance_axes(self):
        store = ResetMemoryStore()
        service = RecommendationService(store, FakeEncoder())
        history = [candidate("joint", ("forest", "standing"), ("blurry",))] * 3
        history += [candidate("extra", ("forest", "sunlight"), ("blurry",))]
        pool = [candidate("a", ("forest", "sunlight"), ("blurry",)),
                candidate("b", ("standing",), ("blurry",)), history[0]]
        all_prepared = service.features.prepare(history + pool)
        keys = tuple(sorted({key for _, exact in all_prepared for key in exact}))
        all_vectors = dense_features(all_prepared, keys)
        precision = np.eye(all_vectors.shape[1]) + all_vectors[:4].T @ all_vectors[:4]
        observed = {A: frozenset(range(4)), B: frozenset(range(3))}
        actual = exploration.rewards(np.linalg.cholesky(precision), keys, all_prepared[4:], all_vectors[4:], observed)
        # An independent dense calculation includes semantics, negative terms and sunlight.
        covariance = np.linalg.solve(precision, np.eye(len(precision)))
        d = np.zeros(len(precision))
        offset = len(precision) - len(keys)
        d[offset + keys.index(A)] = 1
        d[offset + keys.index(B)] = -1
        s = abs(d)
        minus = d @ covariance @ d
        priority = .75 * (1 - s @ covariance @ s / 2) * minus / 2
        expected = np.array([priority * (d @ covariance @ x) ** 2 /
                             ((1 + x @ covariance @ x) * minus) for x in all_vectors[4:]])
        np.testing.assert_allclose(actual, expected, atol=1e-12)
        self.assertGreater(np.ptp(actual), 1e-5)

    def test_pair_search_bounds_and_fixed_or_bound_terms(self):
        keys = [content_key(str(i), "positive") for i in range(40)]
        observed = {key: frozenset(range(3)) for key in keys}
        prepared = [((), {key: 1. for key in keys}), ((), {})]
        selected, pairs = exploration.candidate_pairs(prepared, observed)
        self.assertEqual(len(selected), exploration.MAX_TERMS)
        self.assertEqual(pairs, [], "All terms have identical presence patterns")
        self.assertEqual(exploration.candidate_pairs([prepared[0]] * 2, observed), ([], []))
        varying = [((), {key: 1.}) for key in keys]
        selected, pairs = exploration.candidate_pairs(varying, observed)
        self.assertEqual(len(selected), exploration.MAX_TERMS)
        self.assertLessEqual(len(pairs), 32 * 31 // 2)


class ContrastServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = ResetMemoryStore()
        self.service = RecommendationService(self.store, FakeEncoder())
        self.version = self.service.status().feature_version
        self.pool = (candidate("a", ("forest",)), candidate("b", ("standing",)),
                     candidate("joint", ("forest", "standing")))
        for index in range(3):
            self.learn(str(index), 1, 1)

    def learn(self, artifact, value, revision):
        return self.service.apply_feedback(FeedbackUpdate("local", artifact, revision, value,
            candidate("evidence", ("forest", "forest", "standing"), ("forest",)), self.version))

    def score(self, pool=None, strategy="thompson", seed=123):
        return self.service.score(ScoreRequest("contrast", "local", seed, self.pool if pool is None else pool, strategy))

    def original_scores(self, pool, seed=123):
        prepared = self.service.features.prepare(pool)
        record = self.store.load_policy("local", self.version)
        keys, precision, reward = policy.unpack(record, {key for _, exact in prepared for key in exact})
        _, parameters = policy.scoring_parameters(precision, reward, seed)
        return dense_features(prepared, keys) @ parameters

    def test_bonus_is_bounded_reproducible_and_does_not_sample_or_learn(self):
        before = self.store.load_policy("local", self.version)
        with patch.object(exploration, "is_exploration_round", return_value=True), \
             patch.object(policy, "sample_parameters", side_effect=AssertionError("Do not double explore")), \
             patch.object(self.store, "load_evidence", wraps=self.store.load_evidence) as load:
            first = self.score()
            second = self.score()
        self.assertEqual(first, second)
        self.assertEqual(load.call_count, 1, "Reuse evidence until learning state changes")
        bonuses = [item.score - item.mean_score for item in first.scores]
        self.assertGreater(max(bonuses), 0)
        self.assertGreaterEqual(min(bonuses), -1e-12)
        self.assertLessEqual(max(bonuses), exploration.BONUS_LIMIT)
        winner = max(first.scores, key=lambda item: item.score)
        self.assertLessEqual(max(item.mean_score for item in first.scores) - winner.mean_score, exploration.BONUS_LIMIT)
        self.assertEqual(self.store.load_policy("local", self.version), before)
        np.testing.assert_allclose([item.mean_score for item in first.scores],
                                   [item.score for item in self.score(strategy="mean").scores])

    def test_original_random_stream_on_ordinary_rounds_and_uninformative_pools(self):
        equal = (candidate("one", ("forest",)), candidate("two", ("forest",)))
        fixed = (candidate("one", ("forest", "standing")),
                 candidate("two", ("forest", "standing", "sunlight")))
        bound = (candidate("one", ("forest", "standing")), candidate("two", ("sunlight",)))
        for attempt, pool in [(False, self.pool), (True, equal), (True, fixed), (True, bound)]:
            with self.subTest(attempt=attempt, pool=pool):
                expected = self.original_scores(pool)
                with patch.object(exploration, "is_exploration_round", return_value=attempt):
                    actual = self.score(pool)
                np.testing.assert_array_equal([item.score for item in actual.scores], expected)

    def test_information_reward_changes_a_tied_mean_choice_to_a_separating_candidate(self):
        # Balanced signed feedback leaves the center at zero, but learns the joint direction.
        for index in range(3, 6):
            self.learn(str(index), -1, 1)
        pool = (self.pool[2], self.pool[0], self.pool[1])
        self.assertEqual(max(self.score(pool, strategy="mean").scores, key=lambda row: row.score).candidate_id, "joint")
        with patch.object(exploration, "is_exploration_round", return_value=True):
            scores = self.score(pool).scores
        np.testing.assert_allclose([row.mean_score for row in scores], 0., atol=1e-12)
        self.assertNotEqual(max(scores, key=lambda row: row.score).candidate_id, "joint")

    def test_cold_start_and_mean_never_run_exploration(self):
        with patch.object(exploration, "rewards", side_effect=AssertionError("No contrast solve")):
            self.score(strategy="mean")
            cold = RecommendationService(ResetMemoryStore(), FakeEncoder())
            cold.score(ScoreRequest("cold", "local", 123, self.pool))

    def test_counts_and_cache_follow_rerating_withdrawal_and_external_reset(self):
        with patch.object(exploration, "is_exploration_round", return_value=True):
            self.score()
            observed = self.service._exploration_cache[1]
            self.assertEqual(len(observed[A]), 3)
            self.assertNotIn(content_key("forest", "negative"), observed)
            self.learn("0", -1, 2)
            self.assertIsNone(self.service._exploration_cache)
            self.score()
            self.assertEqual(len(self.service._exploration_cache[1][A]), 3)
            self.learn("0", None, 3)
            self.assertEqual(len(exploration.occurrences(self.store.load_evidence("local", self.version))[A]), 2)
            self.learn("0", 1, 4)
            self.score()
            old_key = self.service._exploration_cache[0]
            self.store.reset_user("local", "external", 0)
            other = RecommendationService(self.store, FakeEncoder())
            for index in range(old_key[-1]):
                other.apply_feedback(FeedbackUpdate("local", str(index), 1, -1,
                    candidate("new", ("forest", "standing", "sunlight")), self.version))
            self.score()
            self.assertNotEqual(self.service._exploration_cache[0], old_key)
            self.assertEqual(self.service._exploration_cache[0][-1], old_key[-1])
            self.assertIn(content_key("sunlight", "positive"), self.service._exploration_cache[1])
            self.service.reset_preferences("local", "reset", 1)
            self.assertIsNone(self.service._exploration_cache)

    def test_real_seed_gate_is_reproducible_and_fallback_uses_original_parameters(self):
        for seed in (0, 1, 12, 123, 999):
            self.assertEqual(exploration.is_exploration_round(seed), exploration.is_exploration_round(seed))
            self.assertEqual(self.score(seed=seed), self.score(seed=seed))
            if not exploration.is_exploration_round(seed):
                np.testing.assert_array_equal([item.score for item in self.score(seed=seed).scores],
                                              self.original_scores(self.pool, seed))


if __name__ == "__main__":
    unittest.main()
