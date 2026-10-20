"""Single-turn OpenAI Images and Gemini Interactions HTTP adapters."""
import asyncio
import base64
import binascii
import json
import re
from urllib.parse import quote, urlsplit, urlunsplit

import aiohttp

from .base import BackendError, CompletedGeneration
from ..network import proxy_for_url

MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 48 * 1024 * 1024
IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
               "image/gif": "gif", "image/avif": "avif"}
DEFAULT_URLS = {"openai": "https://api.openai.com/v1",
                "gemini": "https://generativelanguage.googleapis.com/v1beta"}


def _text(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(c in value for c in "\r\n\x00"):
        raise BackendError(f"{label} must be a non-empty single-line string (up to {limit} characters)")
    return value.strip()


def _url(value, label):
    raw = _text(value, label, 8192)
    try:
        parts = urlsplit(raw)
        valid = parts.scheme in {"http", "https"} and parts.hostname and parts.port != 0
    except ValueError:
        valid = False
    if not valid or parts.username or parts.password or parts.fragment:
        raise BackendError(f"{label} must be an HTTP(S) address without credentials or fragment")
    return parts


def validate_cloud(config, kind):
    result = {"kind": kind}
    for field in ("id", "name", "model"):
        result[field] = _text(config.get(field), field)
    parts = _url(config.get("base_url") or DEFAULT_URLS[kind], "base_url")
    if parts.query:
        raise BackendError("base_url must not contain a query")
    result["base_url"] = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    key = config.get("api_key") or ""
    if not isinstance(key, str) or len(key) > 4096 or any(c in key for c in "\r\n\x00"):
        raise BackendError("api_key must be a single-line string")
    result["api_key"] = key.strip()
    fields = ("size", "quality") if kind == "openai" else ("aspect_ratio", "image_size")
    for field in fields:
        value = config.get(field)
        if value not in (None, ""):
            result[field] = _text(value, field, 100)
    if kind == "openai" and "size" in result and not re.fullmatch(r"auto|[1-9][0-9]{0,4}x[1-9][0-9]{0,4}", result["size"]):
        raise BackendError("size must be auto or WIDTHxHEIGHT")
    if kind == "gemini":
        if "aspect_ratio" in result and not re.fullmatch(r"[1-9][0-9]?:[1-9][0-9]?", result["aspect_ratio"]):
            raise BackendError("aspect_ratio must be WIDTH:HEIGHT")
        if "image_size" in result and result["image_size"] not in {"512", "1K", "2K", "4K"}:
            raise BackendError("image_size must be 512, 1K, 2K or 4K")
    return result


def validate_openai(config):
    return validate_cloud(config, "openai")


def validate_gemini(config):
    return validate_cloud(config, "gemini")


def _image_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and b"avif" in data[8:32]:
        return "image/avif"
    raise BackendError("Generation service returned an unsupported image", uncertain=True)


class CloudBackend:
    kind = ""
    label = ""

    def __init__(self, config, session):
        self.config = validate_cloud(config, self.kind)
        self.session = session

    def _headers(self):
        key = self.config["api_key"]
        if not key:
            return {}
        return {"x-goog-api-key": key} if self.kind == "gemini" else {"Authorization": f"Bearer {key}"}

    async def _json(self, method, path, payload=None):
        submitted = method == "POST"
        url = self.config["base_url"] + path
        try:
            async with self.session.request(method, url, proxy=proxy_for_url(url),
                                            json=payload, headers=self._headers(), allow_redirects=False,
                                            timeout=aiohttp.ClientTimeout(total=300 if submitted else 30)) as response:
                if not 200 <= response.status < 300:
                    # Provider prose can contain credentials, prompts and signed URLs.
                    raise BackendError(f"{self.label} returned HTTP {response.status}",
                                       uncertain=submitted and response.status >= 500)
                raw = bytearray()
                async for part in response.content.iter_chunked(64 * 1024):
                    raw.extend(part)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise BackendError(f"{self.label} response exceeds the size limit", uncertain=submitted)
                try:
                    value = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise BackendError(f"{self.label} returned invalid JSON", uncertain=submitted) from None
                if not isinstance(value, dict):
                    raise BackendError(f"{self.label} returned an unexpected response", uncertain=submitted)
                return value
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            raise BackendError(f"Cannot reach {self.label}; the generation outcome may be unknown" if submitted
                               else f"Cannot reach {self.label}; check the address and credentials",
                               uncertain=submitted) from None

    async def check(self):
        model = self.config["model"]
        if self.kind == "gemini" and model.startswith("models/"):
            model = model[7:]
        try:
            await self._json("GET", "/models/" + quote(model, safe=""))
            return {"ok": True, "message": f"{self.label} model lookup succeeded; image generation and model parameters remain unverified."}
        except BackendError as error:
            return {"ok": False, "message": str(error)}

    async def checkpoints(self):
        return [self.config["model"]]

    async def input_options(self):
        return {}

    @property
    def events_connected(self):
        return False

    async def start_events(self, request_id, notify):
        return False

    async def stop_events(self):
        pass

    async def inspect(self, prompt_id):
        return {"state": "unknown", "outputs": []}

    async def reconcile(self, request_id):
        return None

    async def cancel(self, prompt_id):
        return False

    def _output(self, *, data=None, url=None, mime=None, index=0):
        if data:
            if not isinstance(data, str) or len(data) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
                raise BackendError("Generated image exceeds the size limit", uncertain=True)
            try:
                raw = base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error):
                raise BackendError("Generation service returned invalid image data", uncertain=True) from None
            detected = _image_type(raw)
            if mime and mime != detected:
                raise BackendError("Generated image content does not match its media type", uncertain=True)
            mime = detected
        elif url:
            try:
                _url(url, "image URL")
            except BackendError:
                raise BackendError("Generation service returned an invalid image URL", uncertain=True) from None
            mime = mime or "image/png"
        else:
            raise BackendError("Generation service returned no image data", uncertain=True)
        if mime not in IMAGE_TYPES:
            raise BackendError("Generation service returned an unsupported media type", uncertain=True)
        result = {"node_id": self.kind, "index": index, "filename": f"image-{index}.{IMAGE_TYPES[mime]}",
                  "subfolder": "", "type": "output"}
        result["_b64" if data else "_url"] = data or url
        return result

    async def submit(self, plan, request_id):
        if not isinstance(plan, dict) or not isinstance(plan.get("positive"), str) or not plan["positive"].strip():
            raise BackendError("Generation plan requires a positive prompt")
        if plan.get("negative"):
            raise BackendError(f"{self.label} does not support negative prompts; clear the negative prompt first")
        # Seed capability is checked before the task is queued. Stored jobs may
        # carry an internal randomized seed, which is deliberately never sent.
        config = self.config
        if self.kind == "openai":
            payload = {"model": config["model"], "prompt": plan["positive"], "n": 1}
            payload.update({field: config[field] for field in ("size", "quality") if field in config})
            result = await self._json("POST", "/images/generations", payload)
            images = result.get("data")
            if not isinstance(images, list) or not images:
                raise BackendError("OpenAI Images returned no images; the request will not be repeated automatically", uncertain=True)
            outputs = [self._output(data=item.get("b64_json"), url=item.get("url"), index=index)
                       for index, item in enumerate(images) if isinstance(item, dict)]
        else:
            response_format = {"type": "image", **{field: config[field] for field in ("aspect_ratio", "image_size") if field in config}}
            payload = {"model": config["model"], "input": plan["positive"],
                       "response_format": response_format, "store": False}
            result = await self._json("POST", "/interactions", payload)
            if result.get("status") != "completed":
                raise BackendError("Gemini did not return a completed interaction; the request will not be repeated automatically", uncertain=True)
            steps = result.get("steps")
            images = [block for step in steps if isinstance(step, dict) and step.get("type") == "model_output"
                      and isinstance(step.get("content"), list) for block in step["content"]
                      if isinstance(block, dict) and block.get("type") == "image"] if isinstance(steps, list) else []
            outputs = [self._output(data=item.get("data"), url=item.get("uri"), mime=item.get("mime_type"), index=index)
                       for index, item in enumerate(images)]
        if not outputs:
            raise BackendError(f"{self.label} returned no image outputs; the request will not be repeated automatically", uncertain=True)
        return CompletedGeneration(outputs)

    async def image(self, output):
        if output.get("_b64"):
            try:
                raw = base64.b64decode(output["_b64"], validate=True)
            except (ValueError, binascii.Error):
                raise BackendError("Invalid generated image data") from None
            return raw, _image_type(raw)
        url = output.get("_url")
        _url(url, "image URL")
        try:
            # Separate session: provider API credentials never reach image hosts.
            async with aiohttp.ClientSession() as download:
                async with download.get(url, proxy=proxy_for_url(url), allow_redirects=False,
                                        timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status != 200:
                        raise BackendError(f"Generated image download returned HTTP {response.status}")
                    mime = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                    if mime not in IMAGE_TYPES:
                        raise BackendError("Generated image download returned an unsupported media type")
                    result = bytearray()
                    async for part in response.content.iter_chunked(64 * 1024):
                        result.extend(part)
                        if len(result) > MAX_IMAGE_BYTES:
                            raise BackendError("Generated image exceeds the 32 MB limit")
                    raw = bytes(result)
                    return raw, _image_type(raw)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            raise BackendError("Cannot retrieve the generated image") from None


class OpenAIBackend(CloudBackend):
    kind = "openai"
    label = "OpenAI Images"


class GeminiBackend(CloudBackend):
    kind = "gemini"
    label = "Gemini Interactions"
