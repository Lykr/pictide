"""Autoplay interval HTTP smokes with isolated SQLite and no generation backend."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app


class RoamPlaybackSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        static = self.root / "static"
        static.mkdir()
        static_patch = patch("backend.host.STATIC", static)
        static_patch.start()
        self.addCleanup(static_patch.stop)
        await self.open_app()

    async def open_app(self):
        self.host = create_app(self.root)
        self.app = self.host[APPLICATION]
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()
        await self.app.tasks.stop()

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def put(self, payload):
        response = await self.client.put("/api/settings/roam", json=payload)
        data = await response.json()
        self.assertEqual(response.status, 200, data)
        return data

    async def test_default_event_and_restart_persistence(self):
        response = await self.client.get("/api/settings/roam")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["playback_interval_seconds"], 5)
        stream = self.app.events.stream()
        self.assertEqual((await anext(stream))["topic"], "ready")
        saved = await self.put({"playback_interval_seconds": 12})
        self.assertEqual(saved["playback_interval_seconds"], 12)
        self.assertEqual((await asyncio.wait_for(anext(stream), 1))["topic"], "roam_settings")
        await stream.aclose()
        await self.client.close()
        await self.open_app()
        response = await self.client.get("/api/settings/roam")
        self.assertEqual((await response.json())["playback_interval_seconds"], 12)
        self.assertEqual(self.app.storage.jobs(), [])

    async def test_interval_preserves_settings_epoch_pause_and_invalid_is_atomic(self):
        previous = self.app.roam.save(4, "selected-backend", "selected-preset", 25)
        self.app.storage.pause_roam(previous["epoch"], "Paused smoke")
        saved = await self.put({"playback_interval_seconds": 1})
        self.assertTrue(saved["paused"])
        self.assertEqual(saved["error"], "Paused smoke")
        self.assertEqual(self.app.roam.get(), dict(previous, playback_interval_seconds=1))
        saved = await self.put({"playback_interval_seconds": 600})
        self.assertEqual(saved["playback_interval_seconds"], 600)
        self.assertTrue(saved["paused"])
        before = self.app.roam.get()
        revision = self.app.events.revision
        for value in (0, 601, 1.5, True, None, "5"):
            for payload in ({"playback_interval_seconds": value},
                            {"prefetch_count": 0, "playback_interval_seconds": value}):
                response = await self.client.put("/api/settings/roam", json=payload)
                self.assertEqual(response.status, 400, payload)
                self.assertIn("error", await response.json())
                self.assertEqual(self.app.roam.get(), before)
        self.assertEqual(self.app.events.revision, revision)
        # Existing full settings requests keep the saved interval.
        saved = await self.put({"prefetch_count": 0, "max_history_images": 30})
        self.assertEqual(saved["playback_interval_seconds"], 600)
        self.assertEqual(saved["max_history_images"], 30)
        self.assertEqual(saved["backend_id"], "selected-backend")
        self.assertEqual(saved["preset_id"], "selected-preset")
        self.assertNotEqual(self.app.roam.get()["epoch"], before["epoch"])
        saved = await self.put({"prefetch_count": 0, "playback_interval_seconds": 8})
        self.assertEqual(saved["playback_interval_seconds"], 8)
        self.assertEqual(self.app.storage.jobs(), [])

    async def test_candidate_count_persists_and_preserves_pause(self):
        response = await self.client.get("/api/settings/roam")
        self.assertEqual((await response.json())["candidate_count"], 4)
        previous = self.app.roam.save(0, "selected-backend", "selected-preset", 25)
        self.app.storage.pause_roam(previous["epoch"], "Paused smoke")
        saved = await self.put({"candidate_count": 7})
        self.assertEqual(saved["candidate_count"], 7)
        self.assertTrue(saved["paused"])
        self.assertEqual(self.app.roam.get()["epoch"], previous["epoch"])
        saved = await self.put({"prefetch_count": 0, "max_history_images": 25,
                               "candidate_count": 12})
        self.assertTrue(saved["paused"])
        self.assertEqual(self.app.roam.get()["epoch"], previous["epoch"])
        for value in (0, 21, 1.5, True, None, "4"):
            response = await self.client.put("/api/settings/roam", json={"candidate_count": value})
            self.assertEqual(response.status, 400)
        self.assertEqual(self.app.roam.get()["candidate_count"], 12)
        await self.client.close()
        await self.open_app()
        response = await self.client.get("/api/settings/roam")
        self.assertEqual((await response.json())["candidate_count"], 12)
        self.assertEqual(self.app.storage.jobs(), [])

    async def test_recommendation_strength_persists_without_invalidating_prefetch(self):
        initial = await self.client.get("/api/settings/roam")
        document = await initial.json()
        self.assertEqual((document["recommendation_strength"], document["strong_candidate_multiplier"]), ("standard", 2))
        previous = self.app.roam.save(0, "selected-backend", "selected-preset", 25)
        self.app.storage.pause_roam(previous["epoch"], "Paused smoke")
        saved = await self.put({"recommendation_strength": "strong", "strong_candidate_multiplier": 3})
        self.assertTrue(saved["paused"])
        saved = await self.put({"prefetch_count": 0, "max_history_images": 25, "recommendation_strength": "standard"})
        self.assertTrue(saved["paused"])
        self.assertEqual(self.app.roam.get()["epoch"], previous["epoch"])
        for payload in ({"recommendation_strength": "invalid"}, {"recommendation_strength": None},
                        *({"strong_candidate_multiplier": value} for value in (0, 6, 1.5, True, None, "2"))):
            response = await self.client.put("/api/settings/roam", json=payload)
            self.assertEqual(response.status, 400)
        await self.client.close()
        await self.open_app()
        response = await self.client.get("/api/settings/roam")
        saved = await response.json()
        self.assertEqual((saved["recommendation_strength"], saved["strong_candidate_multiplier"]), ("standard", 3))
        self.assertEqual(self.app.storage.jobs(), [])
