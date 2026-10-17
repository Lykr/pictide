"""Quick-mode HTTP and immutable workflow smokes, without real generation."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from backend.generation.comfyui import ComfyBackend, validate_comfyui
from backend.generation.workflows import default_txt2img, quick_backend_snapshot
from test_app import FakeBackend, configuration


class QuickModeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        static = root / "static"
        static.mkdir()
        self.static = patch("backend.host.STATIC", static)
        self.static.start()
        self.addCleanup(self.static.stop)
        self.host = create_app(root, lambda config, session: FakeBackend())
        self.app = self.host[APPLICATION]
        self.client = TestClient(TestServer(self.host))
        await self.client.start_server()
        await self.app.tasks.stop()
        config = dict(configuration(), id="local")
        config["workflow"]["3"]["inputs"]["steps"] = 29
        self.config = config
        self.app.storage.save_backend(config)
        self.app.roam.save(2, "local", "neutral")
        self.app.candidates = SimpleNamespace(list_presets=lambda: {"presets": [{"id": "neutral"}]})
        self.app._roam_candidate = lambda context: (SimpleNamespace(positive="blue sky", negative=""), {"positive": "blue sky"})

    async def asyncTearDown(self):
        await self.client.close()

    async def put(self, payload, status=200):
        response = await self.client.put("/api/settings/roam", json=payload)
        data = await response.json()
        self.assertEqual(response.status, status, data)
        return data

    async def ensure(self):
        response = await self.client.post("/api/roam/ensure", json={"anchor_id": None})
        data = await response.json()
        self.assertEqual(response.status, 200, data)
        return data

    async def test_settings_and_task_snapshots_preserve_queued_work_and_backend(self):
        settings = await self.put({"playback_interval_seconds": 8})
        self.assertEqual((settings["quick_mode"], settings["quick_steps_factor"], settings["quick_playback_factor"]), (False, .5, .5))
        normal = (await self.ensure())["job"]
        epoch = self.app.roam.get()["epoch"]
        saved = await self.put({"quick_mode": True, "quick_playback_factor": .25})
        self.assertTrue(saved["quick_mode"])
        self.assertEqual(saved["playback_interval_seconds"], 8)
        self.assertEqual(self.app.roam.get()["epoch"], epoch)
        quick = (await self.ensure())["job"]
        workflow_steps = lambda config: config["workflow"]["3"]["inputs"]["steps"]
        self.assertEqual(workflow_steps(self.app.storage.job_backend(normal["id"])), 29)
        self.assertEqual(workflow_steps(self.app.storage.job_backend(quick["id"])), 15)
        self.assertEqual(workflow_steps(self.app.storage.backend("local")), 29)
        self.assertEqual(self.app.storage.job(normal["id"])["status"], "queued")
        full = {key: value for key, value in self.app.roam.get().items() if key != "epoch"}
        full["quick_steps_factor"] = .25
        await self.put(full)
        self.assertEqual(self.app.roam.get()["epoch"], epoch)
        self.assertEqual(workflow_steps(self.app.storage.job_backend(quick["id"])), 15)
        self.app.storage.complete(normal["id"], [])
        faster = (await self.ensure())["job"]
        self.assertEqual(workflow_steps(self.app.storage.job_backend(faster["id"])), 7)
        self.assertEqual(workflow_steps(self.app.storage.job_backend(quick["id"])), 15)
        await self.put({"quick_mode": False})
        self.assertEqual(self.app.roam.get()["epoch"], epoch)
        manual = self.app.storage.create_job({"request_id":"manual", "backend_id":"local", "positive":"sky", "negative":"", "seed":1})
        self.assertEqual(workflow_steps(self.app.storage.job_backend(manual["id"])), 29)
        # Settings survive construction from the same SQLite database.
        from backend.store.roam_settings import RoamSettings
        self.assertEqual(RoamSettings(self.app.paths).get()["quick_steps_factor"], .25)
        with self.app.storage.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM roam_jobs WHERE discarded_at IS NOT NULL").fetchone()[0], 0)

    async def test_invalid_values_or_ambiguous_steps_do_not_save(self):
        previous = self.app.roam.get()
        for payload in ({"quick_mode":1}, {"quick_steps_factor":0}, {"quick_steps_factor":1.1}, {"quick_playback_factor":True}):
            await self.put(payload, 400)
            self.assertEqual(self.app.roam.get(), previous)
        self.config["workflow"]["other"] = {"class_type":"KSampler", "inputs":{"steps":30}}
        self.app.storage.save_backend(self.config)
        error = await self.put({"quick_mode":True}, 400)
        self.assertIn("采样步数", error["error"])
        self.assertEqual(self.app.roam.get(), previous)
        await self.put({"quick_steps_factor":.4})
        self.assertFalse(self.app.roam.get()["quick_mode"])

    async def test_adapter_preserves_actual_steps_and_binding_rejects_links(self):
        config = validate_comfyui(self.config)
        self.assertEqual(config["bindings"]["steps"], {"node_id":"3", "input":"steps"})
        quick = quick_backend_snapshot(config, .5)
        backend = ComfyBackend(quick, None)
        backend._json = AsyncMock(return_value={"prompt_id":"fake"})
        await backend.submit({"positive":"sky", "negative":"blurry", "seed":123}, "quick-request")
        sent = backend._json.call_args.kwargs["payload"]["prompt"]
        self.assertEqual(sent["3"]["inputs"], {"seed":123,"steps":15})
        self.assertEqual(sent["6"]["inputs"]["text"], "sky")
        self.assertEqual(quick_backend_snapshot(config, .01)["workflow"]["3"]["inputs"]["steps"], 1)
        self.assertEqual(default_txt2img("model")["bindings"]["steps"], {"node_id":"5","input":"steps"})
        config["workflow"]["3"]["inputs"]["steps"] = ["other", 0]
        with self.assertRaisesRegex(Exception, "采样步数"):
            validate_comfyui(config)
