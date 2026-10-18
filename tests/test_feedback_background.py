"""HTTP feedback acknowledges durable state before event-driven learning finishes."""
import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np
from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from backend.recommand.service import RecommendationService
from test_app import FakeBackend, configuration
from test_recommendation_application import CPUEncoder


class FeedbackBackgroundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / "data" / "verification"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="feedback-background-", dir=temporary_root)
        self.root = Path(self.directory.name)
        static = self.root / "static"
        static.mkdir()
        static_patch = patch("backend.host.STATIC", static)
        static_patch.start()
        self.addCleanup(static_patch.stop)
        self.gates = []
        self.fake = FakeBackend()
        await self.open_client()
        response = await self.client.put("/api/backends/local", json=configuration())
        self.assertEqual(response.status, 200)

    async def open_client(self):
        host = create_app(self.root, lambda config, session: self.fake)
        self.app = host[APPLICATION]
        self.app.recommendation = RecommendationService(self.app.recommendation_store, CPUEncoder())
        self.version = self.app.recommendation.status().feature_version
        self.rounds = asyncio.Queue()
        loop = asyncio.get_running_loop()
        original = self.app._sync_recommendation

        def observed_round():
            result = original()
            pending = len(self.app.recommendation_store.pending_feedback("local", self.version))
            loop.call_soon_threadsafe(self.rounds.put_nowait, pending)
            return result

        self.app._sync_recommendation = observed_round
        self.client = TestClient(TestServer(host))
        await self.client.start_server()
        await self.app.tasks.stop()
        # Startup explicitly wakes learning, including replay after a restart.
        await asyncio.wait_for(self.rounds.get(), 5)

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.set()
        await self.client.close()
        self.directory.cleanup()

    def output(self):
        snapshot = {"candidate_id": "standing-forest", "positive": "forest, standing", "negative": "",
                    "terms": [{"text": "forest", "channel": "positive"},
                              {"text": "standing", "channel": "positive"}]}
        state = self.app.storage.ensure_roam("background-test", None, 1,
            {"backend_id": "local", "request_id": "background-output", "positive": snapshot["positive"],
             "negative": "", "seed": 42}, snapshot)
        self.app.storage.complete(state["job"]["id"], [{"node_id": "9", "index": 0, "filename": "test.png"}])
        return self.app.storage.artifacts(source="roam")[0]

    async def rate(self, image, value):
        response = await asyncio.wait_for(self.client.put(
            f"/api/artifacts/{image['id']}/feedback", json={"value": value}), 5)
        payload = await response.json()
        self.assertEqual(response.status, 200, payload)
        self.assertEqual(payload["artifact"]["feedback"], value)
        self.assertEqual(self.app.storage.artifact(image["id"])["feedback"], value)
        return payload

    def block_first_learning(self):
        entered = asyncio.Event()
        release = threading.Event()
        self.gates.append(release)
        loop = asyncio.get_running_loop()
        original = self.app.recommendation.apply_feedback
        calls = []

        def apply(update):
            calls.append(update)
            if len(calls) == 1:
                loop.call_soon_threadsafe(entered.set)
                release.wait()
            return original(update)

        return patch.object(self.app.recommendation, "apply_feedback", side_effect=apply), entered, release, calls

    async def drained(self):
        while await asyncio.wait_for(self.rounds.get(), 5):
            pass

    def policy(self):
        return self.app.recommendation_store.load_policy("local", self.version)

    async def test_http_returns_persisted_feedback_while_learning_is_blocked(self):
        image = self.output()
        blocking, entered, release, calls = self.block_first_learning()
        with blocking:
            request = asyncio.create_task(self.rate(image, 1))
            await asyncio.wait_for(entered.wait(), 5)
            payload = await request
            self.assertFalse(release.is_set())
            self.assertEqual(len(calls), 1)
            self.assertIsNone(self.policy())
            self.assertEqual(len(self.app.recommendation_store.pending_feedback("local", self.version)), 1)
            self.assertIn("artifact_revision", payload)
            release.set()
            await self.drained()
        self.assertEqual(self.policy().evidence_count, 1)

    async def test_rapid_feedback_and_retraction_learn_only_latest_state(self):
        image = self.output()
        blocking, entered, release, calls = self.block_first_learning()
        with blocking:
            request = asyncio.create_task(self.rate(image, 1))
            await asyncio.wait_for(entered.wait(), 5)
            await request
            await self.rate(image, -1)
            await self.rate(image, None)
            self.assertEqual(len(calls), 1, "Learning must remain a single serial worker")
            release.set()
            await self.drained()
        evidence = self.app.recommendation_store.load_evidence("local", self.version)
        self.assertEqual(len(evidence), 1)
        self.assertIsNone(evidence[0].value)
        self.assertEqual(self.policy().evidence_count, 0)
        np.testing.assert_allclose(np.frombuffer(self.policy().reward, dtype="<f8"), 0, atol=1e-12)
        self.assertEqual(self.app.recommendation_store.pending_feedback("local", self.version), ())

    async def test_failed_learning_remains_durable_and_replays_on_startup(self):
        image = self.output()
        with patch.object(self.app.recommendation, "apply_feedback", side_effect=RuntimeError("test failure")):
            with self.assertLogs("backend.application", level="ERROR"):
                await self.rate(image, -1)
                self.assertEqual(await asyncio.wait_for(self.rounds.get(), 5), 1)
        self.assertIsNone(self.policy())
        await self.client.close()
        await self.open_client()
        self.assertEqual(self.app.storage.artifact(image["id"])["feedback"], -1)
        self.assertEqual(self.policy().evidence_count, 1)
        self.assertEqual(self.app.recommendation_store.load_evidence("local", self.version)[0].value, -1)
        self.assertEqual(self.app.recommendation_store.pending_feedback("local", self.version), ())


if __name__ == "__main__":
    unittest.main()
