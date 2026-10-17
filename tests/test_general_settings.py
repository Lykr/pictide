"""General theme settings HTTP smoke tests with isolated local data."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app


class GeneralSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        static = self.root / "static"
        static.mkdir()
        self.static = patch("backend.host.STATIC", static)
        self.static.start()
        self.addCleanup(self.static.stop)
        self.app = create_app(self.root)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def test_default_save_event_and_restart(self):
        response = await self.client.get("/api/settings/general")
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"theme": "system"})
        stream = self.app[APPLICATION].events.stream()
        self.assertEqual((await anext(stream))["topic"], "ready")
        response = await self.client.put("/api/settings/general", json={"theme": "dark"})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"theme": "dark"})
        self.assertEqual((await asyncio.wait_for(anext(stream), 1))["topic"], "general_settings")
        await stream.aclose()
        await self.client.close()
        self.app = create_app(self.root)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.assertEqual(await (await self.client.get("/api/settings/general")).json(), {"theme": "dark"})
        response = await self.client.put("/api/settings/general", json={"theme": "light"})
        self.assertEqual(await response.json(), {"theme": "light"})
        response = await self.client.put("/api/settings/general", json={"theme": "system"})
        self.assertEqual(await response.json(), {"theme": "system"})
        await self.client.close()
        self.app = create_app(self.root)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.assertEqual(await (await self.client.get("/api/settings/general")).json(), {"theme": "system"})
        self.assertEqual(self.app[APPLICATION].storage.jobs(), [])

    async def test_invalid_theme_preserves_saved_value(self):
        await self.client.put("/api/settings/general", json={"theme": "dark"})
        revision = self.app[APPLICATION].events.revision
        for payload in ({}, {"theme": "auto"}, {"theme": "Dark"}, {"theme": None},
                        {"theme": True}, {"theme": []}, {"theme": {}}):
            response = await self.client.put("/api/settings/general", json=payload)
            self.assertEqual(response.status, 400, payload)
            self.assertIn("error", await response.json())
        self.assertEqual(await (await self.client.get("/api/settings/general")).json(), {"theme": "dark"})
        self.assertEqual(self.app[APPLICATION].events.revision, revision)
