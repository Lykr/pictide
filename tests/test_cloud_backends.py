"""Protocol smokes against local HTTP fixtures; no paid generation calls."""
import asyncio
import base64
import unittest
from unittest.mock import patch

import aiohttp
from aiohttp import web

from backend.generation import (BackendError, CompletedGeneration, backend_capabilities,
                                create_backend, validate_backend)
from backend.generation.workflows import checkpoint_models, resolve_backend

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
ENCODED = base64.b64encode(PNG).decode()


def config(kind="openai", url=None, **extra):
    return {"id": kind, "name": kind.title(), "kind": kind, "model": "fixture-image-model",
            "api_key": "private-fixture-token", **({"base_url": url} if url else {}), **extra}


class CloudConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_resolves_without_checkpoint_discovery_or_fake_graph(self):
        for kind in ("openai", "gemini"):
            cleaned = await resolve_backend(config(kind), None)
            self.assertNotIn("workflow", cleaned)
            self.assertNotIn("bindings", cleaned)
            self.assertTrue(cleaned["base_url"].startswith("https://"))
            self.assertEqual(await checkpoint_models(cleaned, None), ["fixture-image-model"])
            capabilities = backend_capabilities(cleaned)
            self.assertTrue(capabilities["cloud"])
            self.assertFalse(any(capabilities[key] for key in ("seed", "negative_prompt", "models", "events", "cancel", "recovery")))

    async def test_invalid_config_rejected_and_empty_options_omitted(self):
        for changes in ({"base_url": "https://user:pass@example.com/v1"}, {"base_url": "file:///tmp"},
                        {"api_key": "x\ny"}, {"size": "large"}, {"model": ""}):
            with self.subTest(changes=changes), self.assertRaises(BackendError):
                validate_backend(config(**changes))
        self.assertNotIn("quality", validate_backend(config(quality="")))
        self.assertNotIn("size", validate_backend(config(size=None)))


class CloudProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.status = 200
        self.raw = None
        self.delay = 0
        self.response = {"data": [{"b64_json": ENCODED}]}
        self.download_auth = []
        app = web.Application()
        app.router.add_post("/v1/images/generations", self.generate)
        app.router.add_post("/v1beta/interactions", self.generate)
        app.router.add_get("/{version}/models/{model}", self.model)
        app.router.add_get("/image.png", self.image)
        app.router.add_get("/redirect", self.redirect)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
        self.session = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()

    async def generate(self, request):
        self.calls.append({"path": request.path, "body": await request.json(), "headers": dict(request.headers)})
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raw is not None:
            return web.Response(text=self.raw, status=self.status)
        return web.json_response(self.response, status=self.status)

    async def model(self, request):
        self.calls.append({"path": request.path, "headers": dict(request.headers)})
        return web.json_response({"id": "fixture-image-model"})

    async def image(self, request):
        self.download_auth.append((request.headers.get("Authorization"), request.headers.get("x-goog-api-key")))
        return web.Response(body=PNG, content_type="image/png")

    async def redirect(self, request):
        self.download_auth.append((request.headers.get("Authorization"), request.headers.get("x-goog-api-key")))
        raise web.HTTPFound("/image.png")

    def backend(self, kind="openai", **extra):
        return create_backend(config(kind, self.url + ("/v1" if kind == "openai" else "/v1beta"), **extra), self.session)

    async def test_openai_base64_and_actual_request_fields(self):
        backend = self.backend(size="1024x1024", quality="low")
        completed = await backend.submit({"positive": "a quiet garden", "negative": "", "seed": 923}, "local-1")
        self.assertIsInstance(completed, CompletedGeneration)
        self.assertEqual(await backend.image(completed.outputs[0]), (PNG, "image/png"))
        self.assertEqual(self.calls[0]["body"], {"model": "fixture-image-model", "prompt": "a quiet garden", "n": 1,
                                                "size": "1024x1024", "quality": "low"})
        self.assertEqual(self.calls[0]["headers"]["Authorization"], "Bearer private-fixture-token")
        self.assertTrue(all(key.startswith("_") or key in {"node_id", "index", "filename", "subfolder", "type"}
                            for key in completed.outputs[0]))

    async def test_url_images_download_without_provider_credentials_and_no_redirects(self):
        self.response = {"data": [{"url": self.url + "/image.png"}]}
        backend = self.backend()
        completed = await backend.submit({"positive": "garden"}, "local-2")
        self.assertEqual(await backend.image(completed.outputs[0]), (PNG, "image/png"))
        self.assertEqual(self.download_auth, [(None, None)])
        self.response = {"data": [{"url": self.url + "/redirect"}]}
        completed = await backend.submit({"positive": "garden"}, "local-3")
        with self.assertRaisesRegex(BackendError, "HTTP 302"):
            await backend.image(completed.outputs[0])
        self.assertEqual(len(self.download_auth), 2)

    async def test_gemini_interactions_only_final_images_and_stateless(self):
        self.response = {"id": "ignored-remote-id", "status": "completed", "steps": [
            {"type": "thought", "summary": [{"type": "image", "data": "not-a-final-image"}]},
            {"type": "model_output", "content": [{"type": "text", "text": "garden"},
                                                  {"type": "image", "data": ENCODED, "mime_type": "image/png"}]}]}
        backend = self.backend("gemini", aspect_ratio="16:9", image_size="2K")
        result = await backend.submit({"positive": "a garden", "negative": "", "seed": 456}, "local-4")
        self.assertEqual(len(result.outputs), 1)
        self.assertEqual(await backend.image(result.outputs[0]), (PNG, "image/png"))
        self.assertEqual(self.calls[0]["body"], {"model": "fixture-image-model", "input": "a garden", "store": False,
                                               "response_format": {"type": "image", "aspect_ratio": "16:9", "image_size": "2K"}})
        self.assertEqual(self.calls[0]["headers"]["x-goog-api-key"], "private-fixture-token")
        self.assertNotIn("Authorization", self.calls[0]["headers"])
        self.assertIsNone(await backend.reconcile("local-4"))
        self.assertFalse(await backend.cancel("anything"))
        self.assertFalse(await backend.start_events("local-4", lambda: None))

    async def test_readonly_check_never_submits_generation(self):
        for kind in ("openai", "gemini"):
            result = await self.backend(kind).check()
            self.assertTrue(result["ok"])
            self.assertIn("unverified", result["message"])
        self.assertEqual([item["path"] for item in self.calls], ["/v1/models/fixture-image-model", "/v1beta/models/fixture-image-model"])

    async def test_unsupported_negative_rejected_before_network(self):
        with self.assertRaisesRegex(BackendError, "negative"):
            await self.backend().submit({"positive": "garden", "negative": "noise"}, "local-5")
        self.assertEqual(self.calls, [])

    async def test_failed_and_malformed_responses_do_not_leak_provider_body(self):
        backend = self.backend()
        for status, body, uncertain in ((401, "private-fixture-token", False),
                                        (500, "private-fixture-token", True),
                                        (200, "private-fixture-token", True)):
            self.status, self.raw = status, body
            with self.subTest(status=status), self.assertRaises(BackendError) as raised:
                await backend.submit({"positive": "garden"}, "local-6")
            self.assertEqual(raised.exception.uncertain, uncertain)
            self.assertNotIn("private-fixture-token", str(raised.exception))
        self.raw = None
        self.response = {"data": [{"b64_json": "invalid base64"}]}
        with self.assertRaises(BackendError) as raised:
            await backend.submit({"positive": "garden"}, "local-7")
        self.assertTrue(raised.exception.uncertain)

    async def test_timeout_marks_outcome_unknown_and_does_not_retry(self):
        backend = self.backend()
        self.delay = 0.3
        timeout = aiohttp.ClientTimeout(total=0.15)
        with patch("backend.generation.cloud.aiohttp.ClientTimeout", return_value=timeout):
            with self.assertRaises(BackendError) as raised:
                await backend.submit({"positive": "garden"}, "local-8")
        self.assertTrue(raised.exception.uncertain)
        self.assertEqual(len(self.calls), 1)
