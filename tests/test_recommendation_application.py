"""Full HTTP feedback -> durable evidence -> reversible combination policy."""
import asyncio
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from aiohttp.test_utils import TestClient, TestServer

from backend.contracts.recommendation import ScoreCandidate, ScoreRequest, ScoreTerm
from backend.host import APPLICATION, create_app
from backend.recommand.service import RecommendationService
from test_app import FakeBackend, configuration


class CPUEncoder:
    version = "integration-encoder-v1"
    dimension = 384
    def available(self):
        return True
    def encode(self, texts):
        vectors = []
        for text in texts:
            vector = np.zeros(384)
            vector[int.from_bytes(hashlib.sha256(text.encode()).digest()[:2], "little") % 384] = 1
            vectors.append(vector)
        return vectors


class RecommendationApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        static = self.root / "static"
        static.mkdir()
        static_patch = patch("backend.host.STATIC", static)
        static_patch.start()
        self.addCleanup(static_patch.stop)
        self.fake = FakeBackend()
        self.host = create_app(self.root, lambda config, session: self.fake)
        self.app = self.host[APPLICATION]
        self.app.recommendation = RecommendationService(self.app.recommendation_store, CPUEncoder())
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()
        await self.app.tasks.stop()
        response = await self.client.put("/api/backends/local", json=configuration())
        self.assertEqual(response.status, 200)
        self.candidate = ScoreCandidate("forest-standing", "forest, standing", "",
                                        (ScoreTerm("forest"), ScoreTerm("standing")))
        self.version = self.app.recommendation.status().feature_version

    async def asyncTearDown(self):
        await self.client.close()

    def output(self, count=2):
        snapshot = {"candidate_id": self.candidate.candidate_id, "positive": self.candidate.positive,
                    "negative": "", "terms": [{"text": t.text, "channel": t.channel, "categories": ["management-only"]}
                                                 for t in self.candidate.terms]}
        state = self.app.storage.ensure_roam("test-epoch", None, 1,
            {"backend_id": "local", "request_id": "integration-output", "positive": self.candidate.positive,
             "negative": "", "seed": 42}, snapshot)
        self.app.storage.complete(state["job"]["id"], [{"node_id": "9", "index": i, "filename": f"{i}.png"}
                                                      for i in range(count)])
        return self.app.storage.artifacts(source="roam")

    async def rate(self, image, value):
        response = await self.client.put(f"/api/artifacts/{image['id']}/feedback", json={"value": value})
        payload = await response.json()
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(payload["artifact"]["feedback"], value)
        return payload

    def policy(self):
        return self.app.recommendation_store.load_policy("local", self.version)

    async def test_signed_http_feedback_is_exclusive_reversible_and_idempotent(self):
        image = self.output(1)[0]
        await self.rate(image, -1)
        disliked = self.policy()
        self.assertEqual(disliked.evidence_count, 1)
        request = ScoreRequest("signed-score", "local", 23, (self.candidate,))
        low = self.app.recommendation.score(request).scores[0].score
        await self.rate(image, -1)
        self.assertEqual(self.policy().revision, disliked.revision)
        await self.rate(image, 1)
        liked = self.policy()
        self.assertEqual(liked.evidence_count, 1)
        self.assertEqual(liked.precision, disliked.precision)
        np.testing.assert_allclose(np.frombuffer(liked.reward, dtype="<f8"),
                                   -np.frombuffer(disliked.reward, dtype="<f8"), atol=1e-12)
        self.assertGreater(self.app.recommendation.score(request).scores[0].score, low)
        await self.rate(image, None)
        restored = self.policy()
        self.assertEqual(restored.evidence_count, 0)
        dim = 768 + len(restored.term_keys)
        np.testing.assert_allclose(np.frombuffer(restored.precision, dtype="<f8").reshape(dim, dim), np.eye(dim), atol=1e-12)
        np.testing.assert_allclose(np.frombuffer(restored.reward, dtype="<f8"), 0, atol=1e-12)
        self.assertEqual(self.app.recommendation_store.pending_feedback("local", self.version), ())

    async def test_negative_failure_replays_on_restart_and_reset_blocks_old_evidence(self):
        image = self.output(1)[0]
        with patch.object(self.app.recommendation, "apply_feedback", side_effect=RuntimeError("simulated failure")):
            with self.assertLogs("backend.application", level="ERROR"):
                await self.rate(image, -1)
        self.assertEqual(self.app.storage.artifact(image["id"])["feedback"], -1)
        self.assertIsNone(self.policy())
        await self.client.close()
        self.host = create_app(self.root, lambda config, session: self.fake)
        self.app = self.host[APPLICATION]
        self.app.recommendation = RecommendationService(self.app.recommendation_store, CPUEncoder())
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()
        await self.app.tasks.stop()
        self.assertEqual(self.policy().evidence_count, 1)
        self.assertEqual(self.app.recommendation_store.load_evidence("local", self.version)[0].value, -1)
        preferences = await (await self.client.get("/api/recommendation/preferences")).json()
        self.assertEqual(preferences["evidence_count"], 1)
        response = await self.client.post("/api/recommendation/preferences/reset", json={"request_id": "signed-reset", "expected_reset_revision": 0})
        self.assertEqual(response.status, 200, await response.text())
        await asyncio.to_thread(self.app._sync_recommendation)
        self.assertIsNone(self.policy())
        self.assertEqual(self.app.storage.artifact(image["id"])["feedback"], -1)
        await self.rate(image, None)
        await self.rate(image, -1)
        self.assertEqual(self.policy().evidence_count, 1)

    async def test_http_likes_are_per_image_idempotent_and_withdraw_exactly(self):
        first, second = self.output()
        await self.rate(first, 1)
        self.assertEqual(self.policy().evidence_count, 1)
        revision = self.policy().revision
        await self.rate(first, 1)
        self.assertEqual(self.policy().revision, revision)
        await self.rate(second, 1)
        self.assertEqual(self.policy().evidence_count, 2)
        await self.rate(first, None)
        self.assertEqual(self.policy().evidence_count, 1)
        await self.rate(second, None)
        record = self.policy()
        self.assertEqual(record.evidence_count, 0)
        dimension = 768 + len(record.term_keys)
        np.testing.assert_allclose(np.frombuffer(record.precision, dtype="<f8").reshape(dimension, dimension),
                                   np.eye(dimension), atol=1e-12)
        np.testing.assert_allclose(np.frombuffer(record.reward, dtype="<f8"), 0, atol=1e-12)
        self.assertEqual(self.app.recommendation_store.pending_feedback("local", self.version), ())

    async def test_failed_learning_keeps_like_and_replays_on_restart(self):
        image = self.output(1)[0]
        with patch.object(self.app.recommendation, "apply_feedback", side_effect=RuntimeError("simulated failure")):
            with self.assertLogs("backend.application", level="ERROR"):
                await self.rate(image, 1)
        self.assertEqual(self.app.storage.artifact(image["id"])["feedback"], 1)
        self.assertEqual(len(self.app.recommendation_store.pending_feedback("local", self.version)), 1)
        self.assertIsNone(self.policy())
        restored = create_app(self.root, lambda config, session: self.fake)[APPLICATION]
        restored.recommendation = RecommendationService(restored.recommendation_store, CPUEncoder())
        await asyncio.to_thread(restored._sync_recommendation)
        self.assertEqual(self.policy().evidence_count, 1)
        self.assertEqual(self.app.recommendation_store.pending_feedback("local", self.version), ())
        await self.rate(image, None)
        self.assertEqual(self.policy().evidence_count, 0)

    async def test_retracted_before_replay_never_becomes_positive_evidence(self):
        image = self.output(1)[0]
        self.app.storage.rate(image["id"], 1)
        self.app.storage.rate(image["id"], None)
        await asyncio.to_thread(self.app._sync_recommendation)
        self.assertEqual(self.policy().evidence_count, 0)
        self.assertEqual(self.app.storage.artifact(image["id"])["feedback"], None)

    async def test_manual_images_save_likes_without_fabricated_terms(self):
        job = self.app.storage.create_job({"backend_id": "local", "request_id": "manual-image-request",
                                          "positive": "forest, standing", "negative": "", "seed": 2})
        self.app.storage.complete(job["id"], [{"node_id": "9", "index": 0}])
        image = self.app.storage.artifacts(source="generate")[0]
        await self.rate(image, 1)
        self.assertIsNone(self.policy())
        self.assertEqual(self.app.recommendation_store.pending_feedback("local", self.version), ())

    async def test_restart_preserves_same_seed_scores_and_capability(self):
        image = self.output(1)[0]
        await self.rate(image, 1)
        request = ScoreRequest("same-score-request", "local", 123, (self.candidate,))
        first = self.app.recommendation.score(request)
        restored = RecommendationService(self.app.recommendation_store, CPUEncoder())
        second = restored.score(request)
        self.assertEqual(first, second)
        response = await self.client.get("/api/bootstrap")
        payload = await response.json()
        self.assertTrue(payload["capabilities"]["preference_learning"])
        self.assertTrue(payload["recommendation"]["available"])
        self.assertEqual(payload["recommendation"]["feature_version"], self.version)

    async def test_missing_derived_state_rebuilds_from_evidence_for_score_and_next_like(self):
        first, second = self.output()
        await self.rate(first, 1)
        request = ScoreRequest("rebuild-score", "local", 123, (self.candidate,))
        # Compare posterior means, independently of Thompson sampling noise/order.
        with patch("backend.recommand.policy.sample", side_effect=lambda matrix, reward, seed: np.linalg.solve(matrix, reward)):
            before = self.app.recommendation.score(request)
            with self.app.storage.connection() as db:
                db.execute("DELETE FROM recommendation_policy WHERE user_id='local' AND feature_version=?", (self.version,))
            after = self.app.recommendation.score(request)
        self.assertAlmostEqual(before.scores[0].score, after.scores[0].score, places=12)
        # Next real evidence change also rebuilds the missing derived state.
        await self.rate(second, 1)
        self.assertEqual(self.policy().evidence_count, 2)
        await self.rate(first, None)
        self.assertEqual(self.policy().evidence_count, 1)

    async def test_cleanup_after_withdrawal_retains_learning_replay_snapshot(self):
        image = self.output(1)[0]
        await self.rate(image, 1)
        self.app.storage.rate(image["id"], None)
        with self.app.storage.connection() as db:
            db.execute("UPDATE artifacts SET deleted_at='2026-10-01' WHERE id=?", (image["id"],))
        await asyncio.to_thread(self.app._sync_recommendation)
        self.assertEqual(self.policy().evidence_count, 0)


if __name__ == "__main__":
    unittest.main()
