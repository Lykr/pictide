import copy
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp import web

from backend.generation import BackendError, create_backend, get_backend_types, validate_backend


def config(url="http://127.0.0.1:8188"):
    return {"id": "local", "name": "Local ComfyUI", "kind": "comfyui", "base_url": url,
            "api_key": "secret-test-key", "workflow": {
                "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
                "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old negative"}},
                "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
                "4": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
                "5": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
            }, "bindings": {"positive": {"node_id": "1", "input": "text"},
                            "negative": {"node_id": "2", "input": "text"},
                            "seed": {"node_id": "3", "input": "seed"}}, "output_nodes": ["4"]}


class ConfigTests(unittest.TestCase):
    def test_clean_copy_and_registry(self):
        source = config()
        cleaned = validate_backend(source)
        cleaned["workflow"]["1"]["inputs"]["text"] = "new"
        self.assertEqual(source["workflow"]["1"]["inputs"]["text"], "old positive")
        self.assertEqual(get_backend_types()[0]["kind"], "comfyui")
        source["bindings"]["seed"] = None
        self.assertNotIn("seed", validate_backend(source)["bindings"])

    def test_invalid_configs(self):
        for change in (
            {"base_url": "file:///tmp"}, {"base_url": "http://user:pass@localhost"},
            {"base_url": "http://localhost/?secret=1"}, {"workflow": {"nodes": []}},
            {"kind": "unknown"}, {"api_key": "x\ny"}, {"output_nodes": ["999"]},
        ):
            with self.subTest(change=change), self.assertRaises(BackendError):
                validate_backend({**config(), **change})
        source = config()
        source["bindings"]["negative"] = source["bindings"]["positive"]
        with self.assertRaises(BackendError):
            validate_backend(source)
        source = config()
        source["workflow"]["1"]["inputs"]["text"] = ["2", 0]
        with self.assertRaises(BackendError):
            validate_backend(source)
        source = config()
        source["workflow"]["3"]["inputs"]["seed"] = True
        with self.assertRaises(BackendError):
            validate_backend(source)


    def test_negative_binding_must_be_explicit_for_accurate_records(self):
        source = config()
        source["bindings"]["negative"] = None
        with self.assertRaises(BackendError):
            validate_backend(source)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.history = {}
        self.queue = {"queue_running": [], "queue_pending": []}
        self.submissions = []
        self.deleted = []
        self.cancel_race = False
        self.request_paths = []
        self.post_status = 200
        self.post_body = {"prompt_id": "job-1"}
        self.post_raw = None
        self.image_bytes = b"image bytes"
        self.image_type = "image/png"
        self.auth = []
        self.image_found = True
        self.last_image_query = None
        self.node_info = {
            "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {}]}}, "output": ["CONDITIONING"]},
            "KSampler": {"input": {"required": {"seed": ["INT", {}]}}, "output": ["LATENT"]},
            "SaveImage": {"input": {"required": {"images": ["IMAGE", {}]}}, "output": [], "output_node": True},
            "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["model.safetensors"], {}]}}, "output": ["MODEL", "CLIP", "VAE"]},
            "LoadImage": {"input": {"required": {"image": [[], {"image_upload": True}]}}, "output": ["IMAGE", "MASK"]},
        }
        app = web.Application()
        app.router.add_get("/system_stats", self.stats)
        app.router.add_get("/object_info", self.object_info)
        app.router.add_get("/object_info/CheckpointLoaderSimple", self.checkpoint_info)
        app.router.add_post("/prompt", self.submit)
        app.router.add_get("/history/{prompt_id}", self.get_history)
        app.router.add_get("/history", self.get_history)
        app.router.add_get("/queue", self.get_queue)
        app.router.add_post("/queue", self.delete_queue)
        app.router.add_get("/view", self.view)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.session = aiohttp.ClientSession()
        self.source = config(f"http://127.0.0.1:{port}")
        self.backend = create_backend(self.source, self.session)

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()

    def record(self, request):
        self.request_paths.append((request.method, request.path))
        self.auth.append(request.headers.get("Authorization"))

    async def stats(self, request):
        self.record(request)
        return web.json_response({"system": {}})

    async def object_info(self, request):
        self.record(request)
        return web.json_response(self.node_info)

    async def checkpoint_info(self, request):
        self.record(request)
        return web.json_response({"CheckpointLoaderSimple": self.node_info.get("CheckpointLoaderSimple", {})})

    async def submit(self, request):
        self.record(request)
        self.submissions.append(await request.json())
        if self.post_raw is not None:
            return web.Response(body=self.post_raw, status=self.post_status)
        return web.json_response(self.post_body, status=self.post_status)

    async def get_history(self, request):
        self.record(request)
        prompt_id = request.match_info.get("prompt_id")
        if prompt_id:
            return web.json_response({prompt_id: self.history[prompt_id]} if prompt_id in self.history else {})
        self.assertEqual(request.query["max_items"], "200")
        return web.json_response(self.history)

    async def get_queue(self, request):
        self.record(request)
        return web.json_response(self.queue)

    async def delete_queue(self, request):
        self.record(request)
        deleted = await request.json()
        self.deleted.append(deleted)
        if self.cancel_race:
            self.queue['queue_running'].extend(self.queue['queue_pending'])
        self.queue['queue_pending'] = [x for x in self.queue['queue_pending'] if x[1] not in deleted['delete']]
        return web.Response(status=200)

    async def view(self, request):
        self.record(request)
        self.last_image_query = dict(request.query)
        if request.method == "HEAD":
            return web.Response(status=200 if self.image_found else 404)
        self.assertEqual(request.query["filename"], "out.png")
        return web.Response(body=self.image_bytes, content_type=self.image_type)

    async def test_check_is_readonly(self):
        result = await self.backend.check()
        self.assertTrue(result["ok"])
        self.assertIn("自定义节点校验", result["message"])
        self.assertEqual(self.request_paths, [("GET", "/system_stats"), ("GET", "/object_info")])
        self.assertTrue(all(x == "Bearer secret-test-key" for x in self.auth))

    async def test_checkpoint_enumeration_is_readonly(self):
        self.assertEqual(await self.backend.checkpoints(), ["model.safetensors"])
        self.assertEqual(self.request_paths, [("GET", "/object_info/CheckpointLoaderSimple")])
        self.node_info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0] = []
        self.assertEqual(await self.backend.checkpoints(), [])
        self.node_info["CheckpointLoaderSimple"] = {"input": "malformed"}
        self.assertEqual(await self.backend.checkpoints(), [])

    async def test_check_missing_inputs_options_and_links(self):
        variants = [
            (lambda graph: graph["3"]["inputs"].clear(), "缺少必填输入 seed"),
            (lambda graph: graph["3"]["inputs"].update({"checkpoint": "missing-model"}), "选项在当前后端不可用"),
            (lambda graph: graph["4"]["inputs"].update({"images": ["absent", 0]}), "目标节点不存在"),
            (lambda graph: graph["4"]["inputs"].update({"images": ["3", 99]}), "输出槽位不存在"),
            (lambda graph: graph["4"]["inputs"].update({"images": ["3", True]}), "连接格式无效"),
        ]
        self.node_info["KSampler"]["input"]["optional"] = {"checkpoint": [["available-model"], {}]}
        for change, expected in variants:
            draft = copy.deepcopy(self.source)
            change(draft["workflow"])
            # Removing a required seed binding would fail the local config check;
            # preflight independently checks this workflow input after omitting its binding.
            draft["bindings"]["seed"] = None
            backend = create_backend(draft, self.session)
            result = await backend.check()
            with self.subTest(expected=expected):
                self.assertFalse(result["ok"])
                self.assertIn(expected, result["message"])
                self.assertNotIn("missing-model", result["message"])
        self.assertTrue(all(method == "GET" for method, _ in self.request_paths))

    async def test_check_ignores_disconnected_inputs_but_not_unknown_classes(self):
        self.backend.config["workflow"]["orphan"] = {"class_type": "KSampler", "inputs": {}}
        self.assertTrue((await self.backend.check())["ok"])
        self.backend.config["workflow"]["orphan"]["class_type"] = "MissingNode"
        result = await self.backend.check()
        self.assertFalse(result["ok"])
        self.assertIn("MissingNode", result["message"])

    async def test_check_input_image_head_subfolder_and_annotation(self):
        graph = self.backend.config["workflow"]
        graph["image"] = {"class_type": "LoadImage", "inputs": {"image": "characters/reference.png [output]"}}
        graph["4"]["inputs"]["images"] = ["image", 0]
        # Dropdown is empty; valid annotated/subdirectory paths still use HEAD.
        self.assertTrue((await self.backend.check())["ok"])
        self.assertEqual(self.last_image_query, {"filename": "reference.png", "subfolder": "characters", "type": "output"})
        self.image_found = False
        result = await self.backend.check()
        self.assertFalse(result["ok"])
        self.assertIn("找不到输入图片", result["message"])
        self.assertNotIn("reference.png", result["message"])
        for path in ("../secret.png", "C:\\secret.png", "/absolute.png", "%2e%2e%2fsecret.png"):
            self.request_paths.clear()
            graph["image"]["inputs"]["image"] = path
            with self.subTest(path=path):
                self.assertFalse((await self.backend.check())["ok"])
                self.assertNotIn(("HEAD", "/view"), self.request_paths)
        self.assertTrue(all(method in {"GET", "HEAD"} for method, _ in self.request_paths))

    async def test_check_requires_output_node(self):
        self.node_info["SaveImage"]["output_node"] = False
        result = await self.backend.check()
        self.assertFalse(result["ok"])
        self.assertIn("没有可执行的输出节点", result["message"])

    async def test_structured_400_uses_allowlisted_diagnostics_only(self):
        private = "private positive text"
        self.post_status = 400
        self.post_body = {
            "error": {"type": "prompt_outputs_failed_validation", "message": private, "details": "secret-test-key"},
            "node_errors": {"1": {"class_type": "secret-test-key", "errors": [
                {"type": "value_not_in_list", "message": private, "details": private,
                 "extra_info": {"input_name": "text", "received_value": private, "input_config": "secret-test-key", "traceback": private}},
                {"type": "secret-test-key", "details": private, "extra_info": {"input_name": private}},
            ]}, private: {"errors": [{"type": "required_input_missing"}]}}
        }
        with self.assertRaises(BackendError) as raised:
            await self.backend.submit({"positive": private, "negative": "private negative", "seed": 1}, "req")
        message = str(raised.exception)
        self.assertFalse(raised.exception.uncertain)
        self.assertIn("节点 1 (CLIPTextEncode) / text", message)
        self.assertIn("选项在当前后端不可用", message)
        for secret in (private, "private negative", "secret-test-key", "received_value", "traceback"):
            self.assertNotIn(secret, message)

    async def test_400_bad_or_oversized_body_is_definitive(self):
        self.post_status = 400
        for raw in (b"not-json secret-test-key", b'{"error":'):
            self.post_raw = raw
            with self.assertRaises(BackendError) as raised:
                await self.backend.submit({"positive": "a", "negative": "b", "seed": 1}, "req")
            self.assertFalse(raised.exception.uncertain)
            self.assertNotIn("secret-test-key", str(raised.exception))
        self.post_raw = None
        with patch("backend.generation.comfyui.MAX_ERROR_BYTES", 2):
            with self.assertRaises(BackendError) as raised:
                await self.backend.submit({"positive": "a", "negative": "b", "seed": 1}, "req")
            self.assertFalse(raised.exception.uncertain)

    async def test_400_body_connection_failure_is_definitive(self):
        async def broken_body():
            raise aiohttp.ClientPayloadError("secret-test-key private prompt")
            yield b""  # Make this an async iterator.
        response = MagicMock()
        response.status = 400
        response.content.iter_chunked.return_value = broken_body()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        with patch.object(self.session, "request", return_value=context):
            with self.assertRaises(BackendError) as raised:
                await self.backend.submit({"positive": "a", "negative": "b", "seed": 1}, "req")
            self.assertFalse(raised.exception.uncertain)
            self.assertNotIn("secret-test-key", str(raised.exception))

    async def test_submit_injects_without_mutation(self):
        before = copy.deepcopy(self.source)
        result = await self.backend.submit({"positive": "sun", "negative": "rain", "seed": 81}, "request-1")
        self.assertEqual(result, "job-1")
        payload = self.submissions[0]
        self.assertEqual(payload["prompt"]["1"]["inputs"]["text"], "sun")
        self.assertEqual(payload["prompt"]["2"]["inputs"]["text"], "rain")
        self.assertEqual(payload["prompt"]["3"]["inputs"]["seed"], 81)
        self.assertEqual(payload["extra_data"], {"pictide_request_id": "request-1"})
        self.assertNotIn("secret-test-key", str(payload))
        self.assertEqual(self.source, before)
        self.assertEqual(self.backend.config["workflow"], before["workflow"])

    async def test_submission_failures_and_uncertainty(self):
        for status, body, uncertain in ((400, {"error": "secret-test-key"}, False),
                                        (503, {}, True), (200, {}, True)):
            self.post_status, self.post_body = status, body
            with self.subTest(status=status), self.assertRaises(BackendError) as raised:
                await self.backend.submit({"positive": "a", "negative": "b", "seed": 1}, "req")
            self.assertEqual(raised.exception.uncertain, uncertain)
            self.assertNotIn("secret-test-key", str(raised.exception))
        for error in (aiohttp.ClientConnectionError("secret-test-key"), TimeoutError("secret-test-key")):
            with self.subTest(error=type(error).__name__), patch.object(self.session, "request", side_effect=error):
                with self.assertRaises(BackendError) as raised:
                    await self.backend.submit({"positive": "a", "negative": "b", "seed": 1}, "req")
                self.assertTrue(raised.exception.uncertain)
                self.assertNotIn("secret-test-key", str(raised.exception))

    async def test_connection_refused_is_definitive_submission_failure(self):
        await self.runner.cleanup()
        with self.assertRaises(BackendError) as raised:
            await self.backend.submit({"positive": "landscape", "negative": "text", "seed": 1}, "offline")
        self.assertFalse(raised.exception.uncertain)
        self.assertNotIn("secret-test-key", str(raised.exception))
        self.assertEqual(self.submissions, [])

    async def test_inspect_states_and_output_filter(self):
        self.assertEqual((await self.backend.inspect("job"))["state"], "unknown")
        self.queue["queue_pending"] = [[1, "job", {}, {}]]
        self.assertEqual((await self.backend.inspect("job"))["state"], "queued")
        self.queue["queue_pending"] = []
        self.queue["queue_running"] = [[1, "job", {}, {}]]
        self.assertEqual((await self.backend.inspect("job"))["state"], "running")
        image = {"filename": "out.png", "subfolder": "today", "type": "output"}
        self.history["job"] = {"outputs": {"4": {"images": [image]}, "5": {"images": [image]}}}
        # Merely having an executed output does not mean the job completed.
        self.assertEqual((await self.backend.inspect("job"))["state"], "running")
        self.history["job"]["status"] = {"completed": True, "status_str": "success"}
        result = await self.backend.inspect("job")
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["outputs"], [{"node_id": "4", "index": 0, **image}])
        self.history["job"]["status"] = {"completed": False, "status_str": "error"}
        self.assertEqual((await self.backend.inspect("job"))["state"], "failed")

    async def test_reconcile_queue_history_and_missing(self):
        record = [1, "job", {}, {"pictide_request_id": "req"}, []]
        self.queue["queue_pending"] = [record]
        self.assertEqual(await self.backend.reconcile("req"), "job")
        self.queue["queue_pending"] = []
        self.history["job"] = {"prompt": record}
        self.assertEqual(await self.backend.reconcile("req"), "job")
        self.assertIsNone(await self.backend.reconcile("other"))

    async def test_cancel_only_owned_pending(self):
        self.queue["queue_running"] = [[1, "job", {}, {"pictide_request_id": "req"}]]
        self.assertFalse(await self.backend.cancel("job"))
        self.queue["queue_pending"] = [[1, "job", {}, {}]]
        self.assertFalse(await self.backend.cancel("job"))
        self.queue["queue_pending"][0][3] = {"pictide_request_id": "req"}
        self.queue["queue_running"] = []
        self.assertTrue(await self.backend.cancel("job"))
        self.assertEqual(self.deleted, [{"delete": ["job"]}])
        self.queue["queue_pending"] = [[1, "raced", {}, {"pictide_request_id": "req"}]]
        self.cancel_race = True
        self.assertFalse(await self.backend.cancel("raced"))
        self.assertNotIn(("POST", "/interrupt"), self.request_paths)

    async def test_image_paths_type_and_size(self):
        raw, content_type = await self.backend.image({"filename": "out.png", "subfolder": "today", "type": "output"})
        self.assertEqual((raw, content_type), (self.image_bytes, "image/png"))
        for filename, folder in (("../out.png", ""), ("C:\\out.png", ""), ("out.png", "../secret"),
                                 ("out.png", "/absolute"), ("%2e%2e%2fout.png", "")):
            with self.subTest(filename=filename, folder=folder), self.assertRaises(BackendError):
                await self.backend.image({"filename": filename, "subfolder": folder})
        with patch("backend.generation.comfyui.MAX_IMAGE_BYTES", 2):
            with self.assertRaises(BackendError):
                await self.backend.image({"filename": "out.png"})
        self.image_type = "text/html"
        with self.assertRaises(BackendError):
            await self.backend.image({"filename": "out.png"})


if __name__ == "__main__":
    unittest.main()
