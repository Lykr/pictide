import asyncio
import base64
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from backend.host import create_app, APPLICATION
from backend.paths import DataPaths
from backend.generation.base import BackendError


def configuration():
    return {"name":"Test backend","kind":"comfyui","base_url":"http://127.0.0.1:8188","api_key":"never-return-this-secret",
        "workflow":{"6":{"class_type":"CLIPTextEncode","inputs":{"text":""}},
            "7":{"class_type":"CLIPTextEncode","inputs":{"text":""}},
            "3":{"class_type":"KSampler","inputs":{"seed":0}},
            "9":{"class_type":"SaveImage","inputs":{"filename_prefix":"test"}}},
        "bindings":{"positive":{"node_id":"6","input":"text"},"negative":{"node_id":"7","input":"text"},"seed":{"node_id":"3","input":"seed"}},
        "output_nodes":["9"]}


class FakeBackend:
    def __init__(self):
        self.submissions = []
        self.cancelled = []
        self.fail_submit = False
        self.unexpected_submit_error = False
        self.pending = False

    @property
    def events_connected(self):
        return False

    async def start_events(self, request_id, notify):
        return False

    async def stop_events(self):
        pass

    async def check(self):
        return {"ok":True,"message":"test backend reachable"}

    async def checkpoints(self):
        return ["test-model.safetensors","second-model.safetensors"]

    async def submit(self, plan, request_id):
        self.submissions.append((dict(plan),request_id))
        if self.unexpected_submit_error:
            raise RuntimeError("Unexpected response decoding failure after acceptance")
        if self.fail_submit:
            raise BackendError("Submission outcome unknown",uncertain=True)
        return "external-" + request_id

    async def inspect(self, prompt_id):
        if self.pending:
            return {"state":"running","outputs":[]}
        return {"state":"completed","outputs":[{"node_id":"9","index":n,"filename":f"test{n}.png","subfolder":"","type":"output"} for n in range(2)]}

    async def reconcile(self, request_id):
        return None

    async def cancel(self, prompt_id):
        self.cancelled.append(prompt_id)
        return False

    async def image(self, descriptor):
        return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="),"image/png"


class ApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.backend = FakeBackend()
        self.data_dir = Path(self.directory.name)/"data"
        self.database = DataPaths(self.data_dir).database
        self.client = TestClient(TestServer(create_app(self.data_dir,lambda config,session:self.backend)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def save(self):
        response = await self.client.put("/api/backends/local",json=configuration())
        self.assertEqual(response.status,200)
        return await response.json()

    async def submit(self, request_id="request-unique-1"):
        payload = {"backend_id":"local","request_id":request_id,"positive":"  library, warm light\n","negative":"blurry","seed":42}
        response = await self.client.post("/api/jobs",json=payload)
        self.assertEqual(response.status,202)
        return (await response.json())["job"]

    async def wait_status(self, iid, status):
        for _ in range(100):
            response = await self.client.get("/api/jobs")
            jobs = (await response.json())["jobs"]
            job = next(j for j in jobs if j["id"]==iid)
            if job["status"] == status:
                return job
            await asyncio.sleep(.03)
        self.fail(f"Job did not become {status}: {job}")

    async def test_full_flow_and_private_key_boundary(self):
        saved = await self.save()
        self.assertNotIn("api_key",saved)
        self.assertTrue(saved["has_api_key"])
        response = await self.client.post("/api/backends/local/check",json={k:v for k,v in configuration().items() if k!="api_key"})
        self.assertTrue((await response.json())["ok"])
        job = await self.submit()
        await self.wait_status(job["id"],"completed")
        same = await self.submit()
        self.assertEqual(same["id"],job["id"])
        self.assertEqual(len(self.backend.submissions),1)
        self.assertEqual(self.backend.submissions[0][0]["positive"],"  library, warm light\n")
        response = await self.client.get("/api/bootstrap")
        data = await response.json()
        self.assertNotIn("never-return-this-secret",str(data))
        self.assertFalse(data["capabilities"]["preference_learning"])
        self.assertEqual(data["artifacts"], [])
        self.assertEqual(data["counts"]["generate"], 2)
        generated = await (await self.client.get("/api/artifacts?source=generate")).json()
        artifact = generated["artifacts"][0]
        self.assertTrue(artifact["seed_applied"])
        for value in [1,1,None,1,None]:
            response = await self.client.put(f"/api/artifacts/{artifact['id']}/feedback",json={"value":value})
            self.assertEqual(response.status,200)
            self.assertEqual((await response.json())["artifact"]["feedback"],value)
        for value in [0, True, False, 1.0, "1", [], {}]:
            with self.subTest(value=value):
                response = await self.client.put(f"/api/artifacts/{artifact['id']}/feedback",json={"value":value})
                self.assertEqual(response.status,400)
                self.assertIn("1、-1 或 null",(await response.json())["error"])
                self.assertIsNone(self.client.server.app[APPLICATION].storage.artifact(artifact["id"])["feedback"])
        response = await self.client.get(f"/api/artifacts/{artifact['id']}/prompts")
        self.assertEqual(await response.json(),{"positive":"  library, warm light\n","negative":"blurry"})
        response = await self.client.get(artifact["image_url"])
        self.assertEqual(response.headers["Content-Type"],"image/png")
        self.assertTrue((await response.read()).startswith(b"\x89PNG"))
        cached = list((self.data_dir/"images").glob("*.png"))
        self.assertEqual(len(cached),2)
        import json
        self.assertEqual(json.loads(cached[0].with_suffix(".json").read_text(encoding="utf-8")),{"positive":"  library, warm light\n","negative":"blurry"})
        async def offline(*args):
            raise BackendError("Backend is offline")
        self.backend.image = offline
        response = await self.client.get(artifact["image_url"])
        self.assertEqual(response.status,200)

    async def test_uncertain_submission_never_retries(self):
        await self.save()
        self.backend.fail_submit = True
        job = await self.submit()
        await self.wait_status(job["id"],"unknown")
        await self.submit()
        await asyncio.sleep(.1)
        self.assertEqual(len(self.backend.submissions),1)

    async def test_unexpected_submission_error_never_retries(self):
        await self.save()
        self.backend.unexpected_submit_error = True
        job = await self.submit()
        await self.wait_status(job["id"],"unknown")
        await self.submit()
        await asyncio.sleep(.1)
        self.assertEqual(len(self.backend.submissions),1)

    async def test_cursor_api_and_collection_total(self):
        await self.save()
        job = await self.submit()
        await self.wait_status(job["id"],"completed")
        response = await self.client.get("/api/artifacts?limit=1")
        first = await response.json()
        self.assertTrue(first["has_more"])
        self.assertEqual(first["total"],2)
        response = await self.client.get("/api/artifacts?limit=1&before="+first["next_cursor"])
        second = await response.json()
        self.assertFalse(second["has_more"])
        self.assertNotEqual(first["artifacts"][0]["id"],second["artifacts"][0]["id"])

    async def test_cancel_running_does_not_create_artifacts(self):
        await self.save()
        self.backend.pending = True
        job = await self.submit()
        await self.wait_status(job["id"],"running")
        response = await self.client.post(f"/api/jobs/{job['id']}/cancel",json={})
        self.assertEqual((await response.json())["job"]["status"],"cancelled")
        self.assertEqual(len(self.backend.cancelled),1)
        self.backend.pending = False
        response = await self.client.get("/api/artifacts")
        self.assertEqual((await response.json())["artifacts"],[])

    async def test_reject_cross_origin_and_rebinding(self):
        response = await self.client.put("/api/backends/local",json=configuration(),headers={"Origin":"https://unrelated.example"})
        self.assertEqual(response.status,403)
        response = await self.client.get("/api/bootstrap",headers={"Host":"unrelated.example"})
        self.assertEqual(response.status,403)
        response = await self.client.post("/api/jobs",data="{}",headers={"Content-Type":"text/plain"})
        self.assertEqual(response.status,415)

    async def test_static_page_and_route_safety(self):
        response = await self.client.get("/")
        self.assertEqual(response.status,200)
        self.assertIn("Pictide",await response.text())
        self.assertIn("frame-ancestors 'none'",response.headers["Content-Security-Policy"])
        response = await self.client.get("/static/../storage.py")
        self.assertEqual(response.status,404)

    async def test_unknown_backend_and_idempotency_conflict(self):
        await self.save()
        await self.submit()
        response = await self.client.post("/api/jobs",json={"backend_id":"local","request_id":"request-unique-1","positive":"changed","seed":42})
        self.assertEqual(response.status,409)
        response = await self.client.put("/api/backends/invalid.id",json=configuration())
        self.assertEqual(response.status,400)

    async def test_default_workflow_without_import(self):
        connection = {"name":"Default text to image","kind":"comfyui","base_url":"http://127.0.0.1:8188","workflow_mode":"default"}
        response = await self.client.post("/api/backends/new/models",json=connection)
        self.assertEqual((await response.json())["models"],["test-model.safetensors","second-model.safetensors"])
        response = await self.client.put("/api/backends/default",json=connection)
        self.assertEqual(response.status,200)
        saved = await response.json()
        self.assertEqual(saved["workflow_mode"],"default")
        self.assertEqual(saved["default_checkpoint"],"test-model.safetensors")
        self.assertFalse(any(n["class_type"]=="LoadImage" for n in saved["workflow"].values()))
        payload = {"backend_id":"default","request_id":"default-request-1","positive":"a landscape","negative":"blurry","seed":42}
        response = await self.client.post("/api/jobs",json=payload)
        job = (await response.json())["job"]
        await self.wait_status(job["id"],"completed")
        response = await self.client.get("/api/bootstrap")
        data = await response.json()
        self.assertEqual(Path(data["data_directory"]),self.data_dir)
        self.assertEqual(Path(data["database_path"]),self.database)

    async def test_empty_custom_workflow_falls_back_and_invalid_model_rejected(self):
        connection = {"name":"Empty fallback","kind":"comfyui","base_url":"http://127.0.0.1:8188","workflow_mode":"custom","workflow":{}}
        response = await self.client.put("/api/backends/default",json=connection)
        self.assertEqual(response.status,200)
        self.assertEqual((await response.json())["workflow_mode"],"default")
        response = await self.client.put("/api/backends/default",json={**connection,"default_checkpoint":"missing-model.safetensors"})
        self.assertEqual(response.status,400)
