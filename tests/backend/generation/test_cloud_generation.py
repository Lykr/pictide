"""Application-level cloud generation smokes; all service traffic stays local."""
import asyncio
import base64
import tempfile
import unittest
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from tests.backend.application.test_app import configuration


PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="


class CloudGenerationSmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.requests = []
        self.started = asyncio.Queue()
        self.gates = {}
        provider = web.Application()
        provider.router.add_get("/v1/models/{model}", lambda request: web.json_response({"id": request.match_info["model"]}))
        provider.router.add_get("/v1beta/models/{model}", lambda request: web.json_response({"name": request.match_info["model"]}))
        provider.router.add_post("/v1/images/generations", self.generate)
        provider.router.add_post("/v1beta/interactions", self.generate)
        self.provider = TestServer(provider)
        await self.provider.start_server()
        self.client = TestClient(TestServer(create_app(Path(self.directory.name) / "data")))
        await self.client.start_server()
        self.application = self.client.server.app[APPLICATION]

    async def asyncTearDown(self):
        for gate in self.gates.values():
            gate.set()
        await self.client.close()
        await self.provider.close()
        self.directory.cleanup()

    async def generate(self, request):
        payload = await request.json()
        self.requests.append((request.path, payload, dict(request.headers)))
        prompt = payload.get("prompt", payload.get("input"))
        self.started.put_nowait(prompt)
        if prompt in self.gates:
            await self.gates[prompt].wait()
        if prompt == "invalid response":
            return web.Response(text="malformed successful response")
        if request.path.endswith("interactions"):
            return web.json_response({"id": "interaction-123", "status": "completed", "steps": [
                {"type": "model_output", "content": [{"type": "image", "mime_type": "image/png", "data": PNG}]}]})
        return web.json_response({"data": [{"b64_json": PNG}]})

    def config(self, kind="openai"):
        return {"kind": kind, "name": kind, "base_url": str(self.provider.make_url("/v1" if kind == "openai" else "/v1beta")),
                "api_key": "mock-cloud-secret", "model": "mock-image"}

    async def save(self, kind="openai"):
        response = await self.client.put("/api/backends/cloud", json=self.config(kind))
        self.assertEqual(response.status, 200, await response.text())
        return await response.json()

    async def submit(self, prompt, **options):
        return await self.client.post("/api/jobs", json={"backend_id": "cloud", "request_id": "request-" + prompt,
            "positive": prompt, "negative": "", "seed": -1, **options})

    async def wait_status(self, iid, status):
        async with asyncio.timeout(3):
            while True:
                job = self.application.storage.job(iid)
                if job["status"] == status:
                    return job
                await asyncio.sleep(.01)

    async def test_openai_round_trip_keeps_private_transport_out_of_storage(self):
        saved = await self.save()
        self.assertNotIn("api_key", saved)
        self.assertTrue(saved["capabilities"]["cloud"])
        self.assertFalse(saved["capabilities"]["seed"])
        checked = await self.client.post("/api/backends/cloud/check", json=self.config())
        self.assertTrue((await checked.json())["ok"])
        self.assertEqual(self.requests, [])
        response = await self.submit("garden")
        self.assertEqual(response.status, 202)
        job = (await response.json())["job"]
        completed = await self.wait_status(job["id"], "completed")
        self.assertIsNone(completed["backend_prompt_id"])
        self.assertFalse(completed["seed_applied"])
        self.assertEqual(completed["backend_kind"], "openai")
        artifact = self.application.storage.artifacts(source="generate")[0]
        self.assertEqual(artifact["backend_kind"], "openai")
        self.assertFalse(artifact["seed_applied"])
        image = await self.client.get(artifact["image_url"])
        self.assertEqual(await image.read(), base64.b64decode(PNG))
        with self.application.storage.connection() as db:
            descriptor = db.execute("SELECT descriptor FROM artifacts").fetchone()[0]
        self.assertNotIn(PNG, descriptor)
        self.assertNotIn("_b64", descriptor)
        self.assertEqual((await (await self.client.get(f"/api/artifacts/{artifact['id']}/prompts")).json()),
                         {"positive": "garden", "negative": ""})
        repeat = await self.submit("garden")
        self.assertEqual((await repeat.json())["job"]["id"], job["id"])
        self.assertEqual(len(self.requests), 1)

    async def test_gemini_parameters_and_unsupported_options(self):
        await self.save("gemini")
        for options in [{"negative": "blurry"}, {"seed": 42}]:
            rejected = await self.submit("invalid options", **options)
            self.assertEqual(rejected.status, 400)
        self.assertEqual(self.requests, [])
        job = (await (await self.submit("sunlight")).json())["job"]
        await self.wait_status(job["id"], "completed")
        path, payload, headers = self.requests[0]
        self.assertEqual(path, "/v1beta/interactions")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["response_format"], {"type": "image"})
        self.assertEqual(headers["x-goog-api-key"], "mock-cloud-secret")
        self.assertNotIn("seed", payload)
        self.assertNotIn("negative_prompt", payload)

    async def test_two_cloud_requests_do_not_block_refilling_other_slot(self):
        await self.save()
        self.gates = {"first": asyncio.Event(), "second": asyncio.Event()}
        jobs = {}
        for name in ["first", "second", "third"]:
            jobs[name] = (await (await self.submit(name)).json())["job"]
        started = {await asyncio.wait_for(self.started.get(), 2), await asyncio.wait_for(self.started.get(), 2)}
        self.assertEqual(started, {"first", "second"})
        self.assertEqual(self.application.storage.job(jobs["third"]["id"])["status"], "queued")
        await self.application.tasks.reconcile_unknown()
        await self.application.tasks.tick()
        self.assertEqual(self.application.storage.job(jobs["third"]["id"])["status"], "queued")
        self.assertTrue(all(job["backend_pending"] for job in self.application.storage.dispatch_jobs()))
        self.gates["second"].set()
        self.assertEqual(await asyncio.wait_for(self.started.get(), 2), "third")
        await self.wait_status(jobs["third"]["id"], "completed")
        self.assertEqual(self.application.storage.job(jobs["first"]["id"])["status"], "submitting")
        self.gates["first"].set()
        await self.wait_status(jobs["first"]["id"], "completed")

    async def test_unknown_submission_is_not_retried_and_cloud_selection_disables_prefetch(self):
        await self.save()
        roam = await self.application.roam_settings()
        self.assertEqual(roam["prefetch_count"], 0)
        response = await self.submit("invalid response")
        job = (await response.json())["job"]
        await self.wait_status(job["id"], "unknown")
        await self.application.tasks.reconcile_unknown()
        await self.application.tasks.tick()
        self.assertEqual(len(self.requests), 1)
        next_job = (await (await self.submit("after uncertainty")).json())["job"]
        await self.wait_status(next_job["id"], "completed")
        await self.client.put("/api/backends/local", json=configuration())
        await self.application.roam_settings({"backend_id": "local", "prefetch_count": 2})
        switched = await self.application.roam_settings({"backend_id": "cloud", "prefetch_count": 2})
        self.assertEqual(switched["prefetch_count"], 0)
        enabled = await self.application.roam_settings({"backend_id": "cloud", "prefetch_count": 1})
        self.assertEqual(enabled["prefetch_count"], 1)

    async def test_interrupted_cloud_request_remains_unknown_after_worker_restart(self):
        await self.save()
        self.gates["interrupted"] = asyncio.Event()
        job = (await (await self.submit("interrupted")).json())["job"]
        self.assertEqual(await asyncio.wait_for(self.started.get(), 2), "interrupted")
        await self.application.tasks.stop()
        await self.application.tasks.start()
        self.assertEqual(self.application.storage.job(job["id"])["status"], "unknown")
        next_job = (await (await self.submit("after restart")).json())["job"]
        await self.wait_status(next_job["id"], "completed")
        self.assertEqual([entry[1]["prompt"] for entry in self.requests].count("interrupted"), 1)
