"""General interface preferences HTTP smoke tests with isolated local data."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from backend.store.general_settings import GeneralSettings


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

    async def test_default_partial_save_event_and_restart(self):
        response = await self.client.get("/api/settings/general")
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"theme": "system", "language": "system", "image_transitions": True})
        stream = self.app[APPLICATION].events.stream()
        self.assertEqual((await anext(stream))["topic"], "ready")
        response = await self.client.put("/api/settings/general", json={"theme": "dark"})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"theme": "dark", "language": "system", "image_transitions": True})
        self.assertEqual((await asyncio.wait_for(anext(stream), 1))["topic"], "general_settings")
        await stream.aclose()
        response = await self.client.put("/api/settings/general", json={"language": "en"})
        self.assertEqual(await response.json(), {"theme": "dark", "language": "en", "image_transitions": True})
        response = await self.client.put("/api/settings/general", json={"theme": "system"})
        self.assertEqual(await response.json(), {"theme": "system", "language": "en", "image_transitions": True})
        response = await self.client.put("/api/settings/general", json={"image_transitions": False})
        self.assertEqual(await response.json(),
                         {"theme": "system", "language": "en", "image_transitions": False})
        await self.client.close()
        self.app = create_app(self.root)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.assertEqual(await (await self.client.get("/api/settings/general")).json(),
                         {"theme": "system", "language": "en", "image_transitions": False})
        responses = await asyncio.gather(
            self.client.put("/api/settings/general", json={"theme": "light"}),
            self.client.put("/api/settings/general", json={"language": "zh-CN"}))
        self.assertTrue(all(response.status == 200 for response in responses))
        self.assertEqual(await (await self.client.get("/api/settings/general")).json(),
                         {"theme": "light", "language": "zh-CN", "image_transitions": False})
        response = await self.client.put("/api/settings/general", json={"language": "system"})
        self.assertEqual(await response.json(), {"theme": "light", "language": "system", "image_transitions": False})
        self.assertEqual(self.app[APPLICATION].storage.jobs(), [])

    async def test_invalid_values_preserve_saved_preferences(self):
        await self.client.put("/api/settings/general", json={"theme": "dark", "language": "en", "image_transitions": True})
        revision = self.app[APPLICATION].events.revision
        for payload in ({}, {"theme": "auto"}, {"theme": "Dark"}, {"theme": None},
                        {"theme": True}, {"theme": []}, {"theme": {}}, {"language": "fr"},
                        {"language": None}, {"language": []},
                        {"image_transitions": 0}, {"image_transitions": 1},
                        {"image_transitions": "true"}, {"image_transitions": None},
                        {"image_transitions": []}, {"theme": "light", "language": "invalid"}):
            response = await self.client.put("/api/settings/general", json=payload)
            self.assertEqual(response.status, 400, payload)
            self.assertIn("error", await response.json())
        self.assertEqual(await (await self.client.get("/api/settings/general")).json(),
                         {"theme": "dark", "language": "en", "image_transitions": True})
        self.assertEqual(self.app[APPLICATION].events.revision, revision)

    async def test_existing_explicit_theme_is_preserved(self):
        database = self.root / "previous.sqlite3"
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("CREATE TABLE general_settings (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "theme TEXT NOT NULL CHECK(theme IN ('light','dark')))")
            db.execute("INSERT INTO general_settings VALUES(1, 'dark')")
        settings = GeneralSettings(SimpleNamespace(database=database))
        self.assertEqual(settings.get(), {"theme": "dark", "language": "system", "image_transitions": True})
        self.assertEqual(settings.save({"language": "en"}), {"theme": "dark", "language": "en", "image_transitions": True})
        self.assertEqual(settings.save({"theme": "system"}), {"theme": "system", "language": "en", "image_transitions": True})

    async def test_existing_theme_and_language_are_preserved(self):
        database = self.root / "previous-language.sqlite3"
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("CREATE TABLE general_settings (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "theme TEXT NOT NULL, language TEXT NOT NULL)")
            db.execute("INSERT INTO general_settings VALUES(1, 'dark', 'zh-CN')")
        settings = GeneralSettings(SimpleNamespace(database=database))
        self.assertEqual(settings.get(),
                         {"theme": "dark", "language": "zh-CN", "image_transitions": True})
        self.assertEqual(settings.save({"image_transitions": False}),
                         {"theme": "dark", "language": "zh-CN", "image_transitions": False})
        settings = GeneralSettings(SimpleNamespace(database=database))
        self.assertEqual(settings.get(),
                         {"theme": "dark", "language": "zh-CN", "image_transitions": False})
