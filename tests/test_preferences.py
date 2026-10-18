"""Preference inspection and reset through the approved module boundaries."""
import asyncio
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from backend.contracts.recommendation import FeedbackUpdate, ResetState
from backend.recommand import RecommendationService
from backend.recommand import policy
from backend.recommand.features import SEMANTIC_DIMENSION, content_key
import test_recommendation_application as app_tests
from test_recommendation_core import MemoryStore, FakeEncoder, candidate


class PreferenceInspectionTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.encoder = FakeEncoder()
        self.service = RecommendationService(self.store, self.encoder)
        self.version = self.service.status().feature_version

    def learn(self, terms=("forest",), negative=(), image="image", revision=1, value=1):
        item = candidate(positive=terms, negative=negative)
        self.service.apply_feedback(FeedbackUpdate("local", image, revision, value, item, self.version))

    def test_view_is_readonly_posterior_center_and_per_image_counts(self):
        self.learn(("forest", "forest", "standing"), ("blurry",))
        self.learn(("forest", "sitting"), image="second", value=-1)
        state = self.store.load_policy("local", self.version)
        keys, precision, reward = policy.unpack(state)
        factor = policy.validate(precision, reward)
        center = policy._triangular_solve(factor.T, policy._triangular_solve(factor, reward, True), False)
        vectors = dict(self.store.vectors)
        with patch.object(self.encoder, "encode", side_effect=AssertionError("Viewing encoded text")), \
             patch.object(self.store, "save_vectors", side_effect=AssertionError("Viewing wrote cache")), \
             patch.object(self.store, "commit_feedback", side_effect=AssertionError("Viewing learned")), \
             patch.object(policy, "sample", side_effect=AssertionError("Viewing sampled")):
            view = self.service.preferences("local")
        self.assertTrue(view.available)
        self.assertEqual((view.evidence_count, view.term_count, view.page_size), (2, 4, 15))
        forest = next(t for t in view.terms if t.text == "forest")
        self.assertEqual(forest.evidence_count, 2, "Duplicate terms count once per image")
        for term in view.terms:
            axis = SEMANTIC_DIMENSION + keys.index(content_key(term.text, term.channel))
            self.assertAlmostEqual(term.weight, float(center[axis]), places=12)
        self.assertEqual(self.store.load_policy("local", self.version), state)
        self.assertEqual(self.store.vectors, vectors)

    def test_pagination_stable_and_withdrawn_indices_not_shown(self):
        self.learn(tuple(f"neutral {index:02}" for index in range(25)))
        first = self.service.preferences("local")
        last = self.service.preferences("local", 999)
        self.assertEqual((len(first.terms), len(last.terms), last.page, last.total_pages), (15, 10, 2, 2))
        self.assertFalse(set(first.terms) & set(last.terms))
        self.assertEqual(self.service.preferences("local"), first)
        self.learn(tuple(f"neutral {index:02}" for index in range(25)), value=None, revision=2)
        empty = self.service.preferences("local")
        self.assertTrue(empty.available)
        self.assertEqual((empty.evidence_count, empty.term_count, empty.terms), (0, 0, ()))

    def test_unavailable_encoder_still_returns_reset_metadata(self):
        self.encoder.ready = False
        with patch.object(self.store, "get_reset_state", return_value=ResetState(3, 12, "2026-01-01")):
            view = self.service.preferences("local")
        self.assertFalse(view.available)
        self.assertEqual((view.reset_revision, view.reset_at), (3, "2026-01-01"))

    def test_missing_or_corrupt_policy_reports_unavailable_without_repair(self):
        self.learn()
        state = self.store.states.pop(("local", self.version))
        self.assertFalse(self.service.preferences("local").available)
        self.assertNotIn(("local", self.version), self.store.states)
        self.store.states[("local", self.version)] = replace(state, reward=b"corrupt")
        self.assertFalse(self.service.preferences("local").available)
        self.assertEqual(self.store.states[("local", self.version)].reward, b"corrupt")

    def test_snapshot_retries_after_interleaved_reset(self):
        self.learn()
        values = iter([ResetState(), ResetState(), ResetState(1, 1, "now"), ResetState(1, 1, "now"), ResetState(1, 1, "now")])
        with patch.object(self.store, "get_reset_state", side_effect=lambda user: next(values)):
            view = self.service.preferences("local")
        self.assertTrue(view.available)
        self.assertEqual(view.reset_revision, 1)

    def test_interleaved_reset_and_new_policy_with_same_revision_retries(self):
        self.learn(("old forest",))
        reset = ResetState()
        original = self.store.load_policy
        reads = 0
        other = RecommendationService(self.store, self.encoder)
        def read(user, version):
            nonlocal reads, reset
            reads += 1
            if reads == 2:
                self.store.states.clear()
                self.store.evidence.clear()
                reset = ResetState(1, 1, "now")
                update = FeedbackUpdate("local", "new", 2, 1, candidate(positive=("new beach",)), self.version)
                other.apply_feedback(update)
            return original(user, version)
        with patch.object(self.store, "get_reset_state", side_effect=lambda user: reset), \
             patch.object(self.store, "load_policy", side_effect=read):
            view = self.service.preferences("local")
        self.assertTrue(view.available)
        self.assertEqual(view.state_revision, 1)
        self.assertEqual(view.reset_revision, 1)
        self.assertEqual([t.text for t in view.terms], ["new beach"])

    def test_old_feedback_is_ignored_after_reset(self):
        item = candidate()
        with patch.object(self.store, "get_reset_state", return_value=ResetState(1, 4, "now")):
            response = self.service.apply_feedback(FeedbackUpdate("local", "old", 4, -1, item, self.version))
        self.assertEqual(response.status, "unchanged")
        self.assertEqual(self.store.states, {})
        self.assertEqual(self.encoder.calls, [])

    def test_validation(self):
        for page in (True, 0, -1, 1.5, "1"):
            with self.assertRaises(ValueError):
                self.service.preferences("local", page)
        for revision in (True, -1, 1.5, "1"):
            with self.assertRaises(ValueError):
                self.service.reset_preferences("local", "request", revision)


class PreferenceHTTPTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = app_tests.RecommendationApplicationTests.asyncSetUp
    asyncTearDown = app_tests.RecommendationApplicationTests.asyncTearDown
    observe_learning = app_tests.RecommendationApplicationTests.observe_learning
    output = app_tests.RecommendationApplicationTests.output
    rate = app_tests.RecommendationApplicationTests.rate
    policy = app_tests.RecommendationApplicationTests.policy

    async def reset(self, request="reset", revision=0):
        response = await self.client.post("/api/recommendation/preferences/reset",
            json={"request_id": request, "expected_reset_revision": revision})
        data = await response.json()
        self.assertEqual(response.status, 200, data)
        return data

    async def test_full_preferences_export_reuses_view_and_preserves_state(self):
        empty = await (await self.client.get("/api/recommendation/preferences?all=1")).json()
        self.assertTrue(empty["available"])
        self.assertEqual(empty["terms"], [])
        self.candidate = candidate(positive=tuple(f"neutral {index:02}" for index in range(25)))
        await self.rate(self.output(1)[0], 1)
        before = self.policy()
        jobs = self.app.storage.jobs()
        with patch.object(self.app, "_sync_recommendation", side_effect=AssertionError("Export learned")), \
             patch.object(self.app.recommendation.encoder, "encode", side_effect=AssertionError("Export encoded")):
            first = await (await self.client.get("/api/recommendation/preferences")).json()
            last = await (await self.client.get("/api/recommendation/preferences?page=2")).json()
            full = await (await self.client.get("/api/recommendation/preferences?all=1")).json()
        self.assertEqual((len(first["terms"]), len(last["terms"]), len(full["terms"])), (15, 10, 25))
        self.assertEqual(full["terms"], first["terms"] + last["terms"])
        self.assertEqual((full["page"], full["total_pages"], full["term_count"]), (1, 1, 25))
        self.assertEqual(full["state_revision"], first["state_revision"])
        self.assertEqual(full["feature_version"], self.version)
        self.assertEqual(self.policy(), before)
        self.assertEqual(self.app.storage.jobs(), jobs)
        with patch.object(self.app.recommendation.encoder, "available", return_value=False):
            unavailable = await (await self.client.get("/api/recommendation/preferences?all=1")).json()
            self.assertFalse(unavailable["available"])
        self.assertEqual((await self.client.get("/api/recommendation/preferences?all=2")).status, 400)

    async def test_http_reset_retains_likes_restart_and_version_no_resurrection(self):
        image = self.output(1)[0]
        await self.rate(image, 1)
        jobs = self.app.storage.jobs()
        view = await (await self.client.get("/api/recommendation/preferences")).json()
        self.assertEqual((view["evidence_count"], view["term_count"]), (1, 2))
        result = await self.reset()
        self.assertEqual(result["reset_revision"], 1)
        self.assertEqual(self.app.storage.artifact(image["id"])["feedback"], 1)
        self.assertEqual(self.app.storage.jobs(), jobs)
        self.assertIsNone(self.policy())
        restored = RecommendationService(self.app.recommendation_store, app_tests.CPUEncoder())
        self.app.recommendation = restored
        await asyncio.to_thread(self.app._sync_recommendation)
        self.assertIsNone(self.policy())
        encoder = app_tests.CPUEncoder()
        encoder.version = "new-encoder-version"
        self.app.recommendation = RecommendationService(self.app.recommendation_store, encoder)
        await asyncio.to_thread(self.app._sync_recommendation)
        self.assertEqual(self.app.recommendation.preferences("local").evidence_count, 0)
        await self.rate(image, None)
        await self.rate(image, 1)
        self.assertEqual(self.app.recommendation.preferences("local").evidence_count, 1)
        self.assertEqual(await self.reset(), result, "Retry must preserve newer learned preferences")
        self.assertEqual(self.app.recommendation.preferences("local").evidence_count, 1)

    async def test_reset_works_without_encoder_and_clears_pending_old_like(self):
        image = self.output(1)[0]
        self.app.storage.rate(image["id"], 1)
        with patch.object(self.app.recommendation.encoder, "available", return_value=False):
            await self.reset()
            view = await (await self.client.get("/api/recommendation/preferences")).json()
            self.assertFalse(view["available"])
            self.assertEqual(view["reset_revision"], 1)
        await asyncio.to_thread(self.app._sync_recommendation)
        self.assertIsNone(self.policy())
        self.assertEqual(self.app.recommendation_store.pending_feedback("local", self.version), ())

    async def test_http_inputs_and_conflicts(self):
        for query in ("page=0", "page=-1", "page=true", "page=1.5", "page=9007199254740992", "user_id=other"):
            response = await self.client.get("/api/recommendation/preferences?" + query)
            self.assertEqual(response.status, 400, query)
        for payload in ({}, {"request_id": "x", "expected_reset_revision": True},
                        {"request_id": "x", "expected_reset_revision": -1},
                        {"request_id": "x", "expected_reset_revision": 0, "user_id": "other"}):
            response = await self.client.post("/api/recommendation/preferences/reset", json=payload)
            self.assertEqual(response.status, 400)
        await self.reset()
        response = await self.client.post("/api/recommendation/preferences/reset",
            json={"request_id": "different", "expected_reset_revision": 0})
        self.assertEqual(response.status, 409)
        response = await self.client.post("/api/recommendation/preferences/reset",
            json={"request_id": "reset", "expected_reset_revision": 1})
        self.assertEqual(response.status, 409)

    async def test_view_never_drains_pending_feedback_or_generates_jobs(self):
        image = self.output(1)[0]
        self.app.storage.rate(image["id"], 1)
        jobs = self.app.storage.jobs()
        with patch.object(self.app, "_sync_recommendation", side_effect=AssertionError("View drained feedback")), \
             patch.object(self.app.recommendation, "score", side_effect=AssertionError("View scored")):
            response = await self.client.get("/api/recommendation/preferences")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["evidence_count"], 0)
        self.assertIsNone(self.policy())
        self.assertEqual(self.app.storage.jobs(), jobs)


if __name__ == "__main__":
    unittest.main()
