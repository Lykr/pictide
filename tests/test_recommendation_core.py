"""Recommendation numerical behavior, independence and reversible evidence."""
import ast
import dataclasses
import math
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

try:
    import numpy as np
except ImportError:
    np = None

from backend.contracts.recommendation import ResetState, FeedbackUpdate, PolicyRecord, ScoreCandidate, ScoreRequest, ScoreTerm
from backend.recommand import MiniLMEncoder, RecommendationService
from backend.recommand.features import FeatureEncoder, content_key, dense_features, feature_version
from backend.recommand import policy


class MemoryStore:
    def __init__(self):
        self.vectors = {}
        self.states = {}
        self.evidence = {}
        self.conflicts = 0

    def get_reset_state(self, user_id):
        return ResetState()

    def load_vectors(self, version, texts):
        return {text: self.vectors[(version, text)] for text in texts if (version, text) in self.vectors}

    def save_vectors(self, version, vectors):
        self.vectors.update({(version, text): vector for text, vector in vectors.items()})

    def load_policy(self, user, version):
        return self.states.get((user, version))

    def load_evidence(self, user, version):
        return tuple(item for (u, v, _), item in self.evidence.items() if (u, v) == (user, version))

    def evidence_revision(self, user, artifact, version):
        item = self.evidence.get((user, version, artifact))
        return item.revision if item else 0

    def commit_feedback(self, update, state, expected_revision):
        if self.conflicts:
            self.conflicts -= 1
            return False
        current = self.load_policy(update.user_id, update.feature_version)
        if (current.revision if current else 0) != expected_revision:
            return False
        key = (update.user_id, update.feature_version, update.artifact_id)
        if key in self.evidence and self.evidence[key].revision >= update.revision:
            return False
        self.evidence[key] = update
        self.states[(update.user_id, update.feature_version)] = state
        return True


class FakeEncoder:
    dimension = 384
    version = "fake-fixed-v1"
    ready = True
    error = "Offline model unavailable"

    def __init__(self):
        self.calls = []

    def available(self):
        return self.ready

    def encode(self, texts):
        self.calls.append(tuple(texts))
        output = []
        for text in texts:
            vector = [0.] * 384
            vector[sum(text.encode("utf-8")) % 384] = 1.
            output.append(vector)
        return output


def candidate(identifier="a", positive=("forest",), negative=()):
    terms = tuple(ScoreTerm(text, "positive") for text in positive) + tuple(ScoreTerm(text, "negative") for text in negative)
    return ScoreCandidate(identifier, ", ".join(positive), ", ".join(negative), terms)


@unittest.skipIf(np is None, "Recommendation numerical dependencies are not installed")
class RecommendationCoreTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.encoder = FakeEncoder()
        self.service = RecommendationService(self.store, self.encoder)
        self.version = self.service.status().feature_version

    def score(self, candidates, seed=12, user="local"):
        return self.service.score(ScoreRequest("request", user, seed, tuple(candidates)))

    def feedback(self, c=None, liked=True, revision=1, artifact="image", user="local"):
        return self.service.apply_feedback(FeedbackUpdate(user, artifact, revision, liked, c or candidate(), self.version))

    def test_score_covers_combinations_reproducibly(self):
        candidates = [candidate("a", ("forest", "standing")), candidate("b", ("forest", "sitting"))]
        first = self.score(candidates)
        second = self.score(candidates)
        self.assertEqual(first, second)
        self.assertEqual([s.candidate_id for s in first.scores], ["a", "b"])
        self.assertTrue(all(math.isfinite(s.score) for s in first.scores))
        self.assertNotEqual(first.scores[0].score, first.scores[1].score)
        self.assertEqual(self.store.states, {}, "Scoring must not persist a learned policy")

    def test_identical_combinations_share_parameters(self):
        result = self.score([candidate("a"), candidate("b")])
        self.assertEqual(result.scores[0].score, result.scores[1].score)

    def test_cold_start_explores_both_candidates(self):
        winners = set()
        for seed in range(8):
            scores = self.score([candidate("a", ("forest",)), candidate("b", ("beach",))], seed).scores
            winners.add(max(scores, key=lambda item: item.score).candidate_id)
        self.assertEqual(winners, {"a", "b"})

    def test_cache_reuses_text_across_channels_and_ids(self):
        self.score([candidate("a", ("forest",), ("forest",))])
        self.score([candidate("changed-id", ("forest",))])
        self.assertEqual(self.encoder.calls, [("forest",)])
        self.assertNotEqual(content_key("forest", "positive"), content_key("forest", "negative"))

    def test_nfc_same_content_and_internal_text_preserved(self):
        self.assertEqual(content_key(" e\u0301 ", "positive"), content_key("é", "positive"))
        self.assertNotEqual(content_key("a  b", "positive"), content_key("a b", "positive"))
        self.assertNotEqual(content_key("Forest", "positive"), content_key("forest", "positive"))

    def test_features_channel_normalization_and_empty_direction(self):
        prepared = self.service.features.prepare([candidate("a", ("forest", "standing"))])[0]
        semantic, exact = prepared
        self.assertAlmostEqual(float(np.linalg.norm(semantic[:384])), .25)
        self.assertEqual(float(np.linalg.norm(semantic[384:])), 0)
        self.assertAlmostEqual(sum(value ** 2 for value in exact.values()), 1)
        self.assertNotIn("tag", str(exact))

    def test_weight_syntax_preserved_and_snapshot_checked(self):
        c = candidate("a", ("(forest:1.3)", "long black hair"))
        self.score([c])
        self.assertIn("(forest:1.3)", self.encoder.calls[0])
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.score([dataclasses.replace(c, positive="forest")])

    def test_duplicate_ids_bad_channel_and_nonfinite_encoder_rejected(self):
        with self.assertRaises(ValueError):
            self.score([candidate(), candidate()])
        with self.assertRaises(ValueError):
            self.score([ScoreCandidate("a", "forest", "", (ScoreTerm("forest", "tag"),))])
        self.encoder.encode = lambda texts: [[float("nan")] * 384 for _ in texts]
        with self.assertRaisesRegex(ValueError, "finite"):
            self.score([candidate()])
        self.assertFalse(self.store.vectors)

    def test_feedback_updates_exact_posterior(self):
        c = candidate()
        self.assertEqual(self.feedback(c).status, "applied")
        record = self.store.load_policy("local", self.version)
        keys, precision, reward = policy.unpack(record)
        x = dense_features(self.service.features.prepare([c]), keys)[0]
        np.testing.assert_allclose(precision, np.eye(len(x)) + np.outer(x, x))
        np.testing.assert_allclose(reward, x)
        self.assertEqual(record.evidence_count, 1)
        self.assertEqual(record.revision, 1)

    def test_duplicate_and_stale_feedback_is_unchanged(self):
        self.feedback()
        self.assertEqual(self.feedback().status, "unchanged")
        self.feedback(liked=False, revision=2)
        self.assertEqual(self.feedback(revision=1).status, "unchanged")
        self.assertEqual(self.store.load_policy("local", self.version).evidence_count, 0)
        self.assertFalse(self.store.load_evidence("local", self.version)[0].liked)

    def test_unlike_removes_only_that_image_and_can_relike(self):
        self.feedback(artifact="one")
        self.feedback(artifact="two")
        self.feedback(liked=False, revision=2, artifact="one")
        record = self.store.load_policy("local", self.version)
        self.assertEqual(record.evidence_count, 1)
        keys, precision, reward = policy.unpack(record)
        x = dense_features(self.service.features.prepare([candidate()]), keys)[0]
        np.testing.assert_allclose(precision, np.eye(len(x)) + np.outer(x, x), atol=1e-12)
        np.testing.assert_allclose(reward, x, atol=1e-12)
        self.feedback(liked=True, revision=3, artifact="one")
        self.assertEqual(self.store.load_policy("local", self.version).evidence_count, 2)

    def test_complete_withdrawal_restores_unit_prior(self):
        self.feedback()
        self.feedback(liked=False, revision=2)
        record = self.store.load_policy("local", self.version)
        _, precision, reward = policy.unpack(record)
        np.testing.assert_allclose(precision, np.eye(len(reward)), atol=1e-12)
        np.testing.assert_allclose(reward, 0, atol=1e-12)

    def test_likes_raise_mean_score_for_liked_combination(self):
        c = candidate("liked", ("forest",))
        other = candidate("other", ("beach",))
        for i in range(10):
            self.feedback(c, artifact=str(i))
        record = self.store.load_policy("local", self.version)
        prepared = self.service.features.prepare([c, other])
        keys, precision, reward = policy.unpack(record, {key for _, exact in prepared for key in exact})
        factor = policy.validate(precision, reward)
        mean = policy._triangular_solve(factor.T, policy._triangular_solve(factor, reward, True), False)
        scores = dense_features(prepared, keys) @ mean
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[0], .8)

    def test_indices_extend_without_reordering_and_restart_recovers(self):
        self.feedback(candidate("z", ("zebra",)))
        before = self.store.load_policy("local", self.version).term_keys
        self.service = RecommendationService(self.store, FakeEncoder())
        self.feedback(candidate("a", ("apple",)), artifact="other")
        after = self.store.load_policy("local", self.version).term_keys
        self.assertEqual(after[:len(before)], before)
        self.assertEqual(self.service.score(ScoreRequest("r", "local", 1, (candidate(),))).state_revision, 2)

    def test_feedback_cas_retries_and_version_user_isolation(self):
        self.store.conflicts = 2
        self.assertEqual(self.feedback().status, "applied")
        self.assertEqual(self.score([candidate()], user="other").state_revision, 0)
        update = FeedbackUpdate("local", "other", 1, True, candidate(), "different-version")
        self.assertEqual(self.service.apply_feedback(update).status, "pending")
        self.assertEqual(self.store.load_policy("local", self.version).evidence_count, 1)

    def test_bad_state_rebuilt_from_active_evidence(self):
        self.feedback()
        record = self.store.load_policy("local", self.version)
        self.store.states[("local", self.version)] = dataclasses.replace(record, precision=b"broken")
        result = self.score([candidate()])
        self.assertTrue(math.isfinite(result.scores[0].score))
        self.feedback(liked=False, revision=2)
        record = self.store.load_policy("local", self.version)
        _, precision, reward = policy.unpack(record)
        np.testing.assert_allclose(precision, np.eye(len(reward)), atol=1e-12)
        self.assertEqual(record.evidence_count, 0)

    def test_unavailable_encoder_degrades_without_loading_or_learning(self):
        self.encoder.ready = False
        self.assertFalse(self.service.status().available)
        self.assertEqual(self.feedback().status, "pending")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.score([candidate()])
        self.assertFalse(self.encoder.calls)

    def test_full_correlated_sampling_matches_covariance(self):
        precision = np.array([[2., .8], [.8, 1.5]])
        samples = np.array([policy.sample(precision, np.zeros(2), seed) for seed in range(3000)])
        np.testing.assert_allclose(np.cov(samples.T), np.linalg.solve(precision, np.eye(2)), atol=.045)
        self.assertLess(np.cov(samples.T)[0, 1], -.2)

    def test_long_base_term_errors_before_embedding(self):
        encoder = MiniLMEncoder("unused-offline-cache")
        encoder._tokenizer = SimpleNamespace(encode=lambda text: SimpleNamespace(ids=list(range(257))))
        with patch.object(encoder, "available", return_value=True):
            with self.assertRaisesRegex(ValueError, "256 tokens"):
                encoder.encode(["long term"])
        self.assertIsNone(encoder._model)

    def test_corrupt_runtime_model_reports_unavailable(self):
        encoder = MiniLMEncoder("unused-offline-cache")
        encoder._tokenizer = SimpleNamespace(encode=lambda text: SimpleNamespace(ids=[1, 2, 3]))
        encoder._model = SimpleNamespace(embed=lambda *args, **kwargs: (_ for _ in ()).throw(Exception("invalid ONNX")))
        with patch.object(encoder, "available", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "invalid ONNX"):
                encoder.encode(["forest"])
        self.assertIn("invalid ONNX", encoder.error)

    def test_accepted_new_model_fingerprint_clears_unloaded_tokenizer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.onnx"
            model.write_bytes(b"first model fingerprint")
            encoder = MiniLMEncoder(root)
            with patch.object(encoder, "_files", return_value=(root, [model])), \
                 patch("backend.recommand.encoder.importlib.util.find_spec", return_value=object()), \
                 patch("backend.recommand.encoder.package_version", return_value="test"):
                self.assertTrue(encoder.available())
                first_version = encoder.version
                encoder._tokenizer = object()
                model.write_bytes(b"second model fingerprint with a different length")
                self.assertTrue(encoder.available())
                self.assertNotEqual(encoder.version, first_version)
                self.assertIsNone(encoder._tokenizer)

    def test_source_has_no_candidate_or_task_imports(self):
        directory = Path(__file__).parents[1] / "backend" / "recommand"
        for path in directory.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("candidate", (node.module or "").split("."))
                    self.assertNotIn("task", (node.module or "").split("."))

    def test_empty_pool_returns_empty_and_absent_model_is_offline(self):
        self.assertEqual(self.score([]).scores, ())
        encoder = MiniLMEncoder(Path(__file__).parents[1] / "data" / "nonexistent-model")
        self.assertFalse(encoder.available())
        with self.assertRaises(RuntimeError):
            encoder.encode(["forest"])


if __name__ == "__main__":
    unittest.main()
