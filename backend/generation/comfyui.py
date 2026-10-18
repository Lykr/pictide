"""ComfyUI API adapter: deterministic injection, event notifications and HTTP result checks."""
import asyncio
import copy
import json
import re
import uuid
from typing import Callable
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import aiohttp

from .base import BackendError

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 32 * 1024 * 1024
HISTORY_LIMIT = 200
MAX_ERROR_BYTES = 128 * 1024
ERROR_REASONS = {
    "prompt_outputs_failed_validation": "工作流输出未通过校验",
    "prompt_no_outputs": "工作流没有输出节点",
    "missing_node_type": "节点类型未安装或缺失",
    "required_input_missing": "缺少必填输入",
    "value_not_in_list": "选项在当前后端不可用，请检查模型或输入文件",
    "invalid_input_type": "输入类型无效",
    "bad_linked_input": "输入连接格式无效",
    "return_type_mismatch": "连接两端的数据类型不匹配",
    "value_smaller_than_min": "输入低于允许的最小值",
    "value_bigger_than_max": "输入超过允许的最大值",
    "custom_validation_failed": "节点自定义校验失败，请检查输入文件或节点配置",
    "exception_during_validation": "节点校验发生异常",
    "exception_during_inner_validation": "上游节点校验发生异常",
}


def _string(value, label, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BackendError(f"{label} must be a non-empty string (up to {maximum} characters)")
    return value.strip()


def validate_comfyui(config: dict) -> dict:
    if not isinstance(config, dict):
        raise BackendError("Backend configuration must be an object")
    result = {"kind": "comfyui"}
    for key in ("id", "name"):
        result[key] = _string(config.get(key), key)
    raw_url = _string(config.get("base_url"), "base_url", 2048)
    try:
        url = urlsplit(raw_url)
        valid = url.scheme in {"http", "https"} and bool(url.hostname) and url.port != 0
    except ValueError:
        valid = False
    if not valid or url.username or url.password or url.query or url.fragment:
        raise BackendError("base_url must be an HTTP(S) address without credentials, query or fragment")
    result["base_url"] = urlunsplit((url.scheme, url.netloc, url.path.rstrip("/"), "", ""))
    key = config.get("api_key", "")
    if key is None:
        key = ""
    if not isinstance(key, str) or len(key) > 4096 or any(c in key for c in "\r\n"):
        raise BackendError("api_key must be a single-line string")
    result["api_key"] = key.strip()
    workflow = config.get("workflow")
    if not isinstance(workflow, dict) or not workflow or isinstance(workflow.get("nodes"), list):
        raise BackendError("workflow must be an API-format node object; export API format, not the UI workflow")
    if len(workflow) > 2000:
        raise BackendError("workflow contains too many nodes")
    for node_id, node in workflow.items():
        if not isinstance(node_id, str) or not node_id or not isinstance(node, dict):
            raise BackendError("workflow nodes must have string IDs and object values")
        if not isinstance(node.get("class_type"), str) or not node["class_type"].strip() or not isinstance(node.get("inputs"), dict):
            raise BackendError("Each API workflow node requires class_type and inputs")
    try:
        encoded = json.dumps(workflow, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise BackendError("workflow must contain finite JSON values") from None
    if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
        raise BackendError("workflow exceeds the 8 MB limit")
    result["workflow"] = copy.deepcopy(workflow)
    bindings = config.get("bindings")
    if not isinstance(bindings, dict):
        raise BackendError("bindings must define positive and negative inputs")
    result["bindings"] = {}
    for role in ("positive", "negative", "seed"):
        binding = bindings.get(role)
        if role == "seed" and binding is None:
            continue
        if not isinstance(binding, dict):
            raise BackendError(f"bindings.{role} must specify node_id and input")
        node_id = _string(binding.get("node_id"), f"bindings.{role}.node_id")
        input_name = _string(binding.get("input"), f"bindings.{role}.input")
        node = workflow.get(node_id)
        if node is None or input_name not in node["inputs"]:
            raise BackendError(f"bindings.{role} references a missing node input")
        value = node["inputs"][input_name]
        if role == "seed":
            if not isinstance(value, int) or isinstance(value, bool):
                raise BackendError("Seed binding must target an integer input, not a linked input")
        elif not isinstance(value, str):
            raise BackendError(f"bindings.{role} must target a text string, not a linked input")
        result["bindings"][role] = {"node_id": node_id, "input": input_name}
    if result["bindings"]["positive"] == result["bindings"]["negative"]:
        raise BackendError("Positive and negative bindings must target different inputs")
    outputs = config.get("output_nodes", [])
    if outputs is None:
        outputs = []
    if not isinstance(outputs, list) or any(not isinstance(x, str) or x not in workflow for x in outputs):
        raise BackendError("output_nodes must be a list of workflow node IDs")
    result["output_nodes"] = list(dict.fromkeys(outputs))
    if "extra" in config:
        if not isinstance(config["extra"], dict):
            raise BackendError("extra must be an object")
        try:
            json.dumps(config["extra"], allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            raise BackendError("extra must contain finite JSON values") from None
        result["extra"] = copy.deepcopy(config["extra"])
    return result


def _safe_descriptor(output: dict) -> dict:
    if not isinstance(output, dict):
        raise BackendError("Invalid image descriptor")
    filename = output.get("filename")
    subfolder = output.get("subfolder", "")
    kind = output.get("type", "output")
    if kind not in {"output", "temp", "input"}:
        raise BackendError("Invalid image storage type")
    if not isinstance(filename, str) or not filename or len(filename) > 255:
        raise BackendError("Invalid image filename")
    if not isinstance(subfolder, str) or len(subfolder) > 2048:
        raise BackendError("Invalid image subfolder")
    for path in (filename, subfolder):
        decoded = unquote(path)
        if any(c in decoded for c in ("\\", ":", "\x00")) or decoded.startswith("/") or any(p in {".", ".."} for p in decoded.split("/")):
            raise BackendError("Image paths must be relative and cannot contain traversal")
    if "/" in unquote(filename):
        raise BackendError("Image filename cannot contain directories")
    return {"filename": filename, "subfolder": subfolder, "type": kind}


class ComfyBackend:
    def __init__(self, config: dict, session: aiohttp.ClientSession):
        self.config = validate_comfyui(config)
        self.session = session
        self._events_request_id = None
        self._events_client_id = None
        self._events_prompt_id = None
        self._events_ws = None
        self._events_task = None
        self._events_notify = None

    def _set_event_request(self, request_id):
        if self._events_request_id != request_id:
            self._events_request_id = request_id
            self._events_client_id = "pictide-" + str(uuid.uuid5(uuid.NAMESPACE_URL, request_id))
            self._events_prompt_id = None

    @property
    def events_connected(self) -> bool:
        return (self._events_ws is not None and not self._events_ws.closed
                and self._events_task is not None and not self._events_task.done())

    async def start_events(self, request_id: str, notify: Callable[[], None]) -> bool:
        request_id = _string(request_id, "request_id")
        if self._events_request_id == request_id and self.events_connected:
            self._events_notify = notify
            return True
        await self.stop_events()
        self._set_event_request(request_id)
        self._events_notify = notify
        try:
            # Bound the handshake, not the lifetime of a connected stream.
            ws = await asyncio.wait_for(self.session.ws_connect(
                self.config["base_url"] + "/ws", params={"clientId": self._events_client_id},
                headers=self._headers(), heartbeat=30, max_msg_size=MAX_JSON_BYTES,
                timeout=aiohttp.ClientWSTimeout(ws_close=1)), timeout=1)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            self._events_notify = None
            return False
        self._events_ws = ws
        self._events_task = asyncio.create_task(self._receive_events(ws))
        return True

    async def _receive_events(self, ws):
        try:
            async for message in ws:
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    event = json.loads(message.data)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
                    continue
                data, kind = event["data"], event.get("type")
                terminal = kind in ("execution_success", "execution_error", "execution_interrupted")
                terminal = terminal or (kind == "executing" and "node" in data and data["node"] is None)
                if not terminal or not isinstance(data.get("prompt_id"), str):
                    continue
                if self._events_prompt_id is not None and data["prompt_id"] != self._events_prompt_id:
                    continue
                if self._events_notify is not None:
                    self._events_notify()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            pass
        finally:
            if self._events_ws is ws:
                self._events_ws = None
                if self._events_notify is not None:
                    self._events_notify()
            await ws.close()

    async def stop_events(self) -> None:
        ws, task = self._events_ws, self._events_task
        self._events_ws = self._events_task = self._events_notify = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if ws is not None and not ws.closed:
            await ws.close()

    def _redact(self, text):
        value = str(text)
        key = self.config["api_key"]
        if key:
            value = value.replace(key, "[redacted]")
        return value[:700]

    def _headers(self):
        key = self.config["api_key"]
        return {"Authorization": f"Bearer {key}"} if key else {}

    def _label(self, node_id, input_name=None):
        """Only identify known graph metadata, never echo server-supplied prose."""
        node = self.config["workflow"].get(node_id)
        if not isinstance(node, dict):
            return "工作流"
        safe = lambda value: value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value) else "?"
        label = f"节点 {safe(node_id)} ({safe(node['class_type'])})"
        if input_name in node["inputs"]:
            label += f" / {safe(input_name)}"
        return label

    def _rejection(self, payload, status):
        parts = []
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and isinstance(error.get("type"), str):
                reason = ERROR_REASONS.get(error["type"])
                if reason:
                    parts.append(reason)
            node_errors = payload.get("node_errors")
            if isinstance(node_errors, dict):
                for node_id, record in list(node_errors.items())[:20]:
                    if node_id not in self.config["workflow"] or not isinstance(record, dict):
                        continue
                    errors = record.get("errors", [])
                    if not isinstance(errors, list):
                        continue
                    for error in errors[:5]:
                        if not isinstance(error, dict):
                            continue
                        reason = ERROR_REASONS.get(error.get("type")) if isinstance(error.get("type"), str) else None
                        if not reason:
                            reason = "输入校验失败"
                        extra = error.get("extra_info", {})
                        name = extra.get("input_name") if isinstance(extra, dict) else None
                        if not isinstance(name, str):
                            name = None
                        parts.append(f"{self._label(node_id, name)}：{reason}")
        detail = "；".join(dict.fromkeys(parts))
        suffix = f"：{detail}" if detail else "；请检查工作流输入与后端节点配置"
        return self._redact(f"ComfyUI 拒绝请求 (HTTP {status}){suffix}")

    async def _json(self, method, path, *, payload=None, params=None, uncertain=False, allow_empty=False):
        try:
            async with self.session.request(method, self.config["base_url"] + path, json=payload, params=params,
                                            headers=self._headers(), allow_redirects=False,
                                            timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status >= 500:
                    raise BackendError(f"ComfyUI returned HTTP {response.status}", uncertain=uncertain)
                if response.status < 200 or response.status >= 300:
                    # A rejection is definitive even if its diagnostic body is unreadable.
                    diagnostic = None
                    try:
                        raw_error = bytearray()
                        async for part in response.content.iter_chunked(16 * 1024):
                            raw_error.extend(part)
                            if len(raw_error) > MAX_ERROR_BYTES:
                                break
                        if len(raw_error) <= MAX_ERROR_BYTES:
                            diagnostic = json.loads(raw_error)
                    except (ValueError, UnicodeDecodeError, aiohttp.ClientError, asyncio.TimeoutError, OSError):
                        pass
                    raise BackendError(self._rejection(diagnostic, response.status), uncertain=False)
                raw = bytearray()
                async for part in response.content.iter_chunked(64 * 1024):
                    raw.extend(part)
                    if len(raw) > MAX_JSON_BYTES:
                        raise BackendError("ComfyUI response exceeds the 8 MB limit", uncertain=uncertain)
                if allow_empty and not raw:
                    return {}
                try:
                    value = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise BackendError("ComfyUI returned invalid JSON", uncertain=uncertain) from None
                if not isinstance(value, dict):
                    raise BackendError("ComfyUI returned an unexpected response", uncertain=uncertain)
                return value
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            raise BackendError("Cannot reach ComfyUI; check the backend address and server", uncertain=uncertain) from None

    async def checkpoints(self) -> list[str]:
        info = await self._json("GET", "/object_info/CheckpointLoaderSimple")
        schema = info.get("CheckpointLoaderSimple", {})
        inputs = schema.get("input", {}) if isinstance(schema, dict) else {}
        required = inputs.get("required", {}) if isinstance(inputs, dict) else {}
        spec = required.get("ckpt_name", []) if isinstance(required, dict) else []
        options = spec[0] if isinstance(spec, list) and spec else []
        if not isinstance(options, list):
            return []
        key = self.config["api_key"]
        return list(dict.fromkeys(x for x in options if isinstance(x, str) and x and (not key or key not in x)))

    async def input_options(self):
        info = await self._json("GET", "/object_info")
        choices = {}
        for node in self.config["workflow"].values():
            name = node["class_type"]
            schema = info.get(name, {})
            inputs = schema.get("input", {}) if isinstance(schema,dict) else {}
            for kind in ("required","optional"):
                fields = inputs.get(kind,{}) if isinstance(inputs,dict) else {}
                if not isinstance(fields,dict):
                    continue
                for field,spec in fields.items():
                    if not isinstance(spec,list) or not spec:
                        continue
                    values = spec[0] if isinstance(spec[0],list) else spec[1].get("options") if spec[0] == "COMBO" and len(spec)>1 and isinstance(spec[1],dict) else None
                    if isinstance(values,list):
                        choices.setdefault(name,{})[field] = [v for v in values[:2000] if isinstance(v,(str,int,float,bool)) and (not isinstance(v,str) or not self.config["api_key"] or self.config["api_key"] not in v)]
        return choices

    def _preflight(self, info):
        graph = self.config["workflow"]
        issues, image_checks = [], []
        # ComfyUI executes every OUTPUT_NODE, irrespective of the feed display filter.
        roots = [node_id for node_id, node in graph.items()
                 if isinstance(info.get(node["class_type"]), dict) and info[node["class_type"]].get("output_node") is True]
        if not roots:
            return ["工作流没有可执行的输出节点"], []
        reachable, pending = set(), list(roots)
        while pending:
            node_id = pending.pop()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            for value in graph[node_id]["inputs"].values():
                if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and value[0] in graph:
                    pending.append(value[0])
        for node_id in sorted(reachable):
            node = graph[node_id]
            schema = info[node["class_type"]]
            if not isinstance(schema, dict):
                issues.append(f"{self._label(node_id)}：后端节点结构信息无效")
                continue
            inputs = schema.get("input", {})
            if not isinstance(inputs, dict):
                continue
            required, optional = inputs.get("required", {}), inputs.get("optional", {})
            required = required if isinstance(required, dict) else {}
            optional = optional if isinstance(optional, dict) else {}
            for name in required:
                if name not in node["inputs"]:
                    # Input names here originate in a schema; no server error prose is used.
                    issues.append(f"{self._label(node_id)}：缺少必填输入 {name if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', str(name)) else '?'}")
            for name, value in node["inputs"].items():
                spec = required.get(name, optional.get(name))
                label = self._label(node_id, name)
                if isinstance(value, list):
                    if len(value) != 2 or not isinstance(value[0], str) or value[0] not in graph or not isinstance(value[1], int) or isinstance(value[1], bool) or value[1] < 0:
                        issues.append(f"{label}：输入连接格式无效或目标节点不存在")
                        continue
                    source_schema = info.get(graph[value[0]]["class_type"], {})
                    returns = source_schema.get("output") if isinstance(source_schema, dict) else None
                    if isinstance(returns, list) and value[1] >= len(returns):
                        issues.append(f"{label}：连接引用的输出槽位不存在")
                    continue
                if not isinstance(spec, list) or not spec:
                    continue
                if node["class_type"] in {"LoadImage", "LoadImageMask"} and name == "image":
                    try:
                        image_checks.append((label, self._input_image_descriptor(value)))
                    except BackendError:
                        issues.append(f"{label}：输入图片路径无效，请使用安全相对路径")
                    continue
                kind = spec[0]
                options = kind if isinstance(kind, list) else None
                if kind == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
                    options = spec[1].get("options")
                if isinstance(options, list) and value not in options:
                    issues.append(f"{label}：选项在当前后端不可用，请检查模型或节点选项")
        return issues, image_checks

    @staticmethod
    def _input_image_descriptor(value):
        if not isinstance(value, str) or not value:
            raise BackendError("Invalid image input")
        match = re.fullmatch(r"(.*) \[(input|output|temp)\]", value)
        path, kind = (match.group(1), match.group(2)) if match else (value, "input")
        if unquote(path).startswith("/"):
            raise BackendError("Absolute image paths are not allowed")
        subfolder, separator, filename = path.rpartition("/")
        return _safe_descriptor({"filename": filename if separator else path,
                                 "subfolder": subfolder if separator else "", "type": kind})

    async def _image_exists(self, descriptor):
        try:
            async with self.session.head(self.config["base_url"] + "/view", params=descriptor,
                                         headers=self._headers(), allow_redirects=False,
                                         timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 404:
                    return False
                if response.status != 200:
                    raise BackendError(f"无法只读检查输入图片 (HTTP {response.status})")
                return True
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            raise BackendError("无法连接后端检查输入图片") from None

    async def check(self) -> dict:
        try:
            await self._json("GET", "/system_stats")
            info = await self._json("GET", "/object_info")
            missing = {node["class_type"] for node in self.config["workflow"].values()} - info.keys()
            if missing:
                labels = [self._label(node_id) for node_id, node in self.config["workflow"].items() if node["class_type"] in missing]
                return {"ok": False, "message": self._redact("节点类型未安装：" + "、".join(labels))}
            issues, image_checks = self._preflight(info)
            for label, descriptor in image_checks:
                if not await self._image_exists(descriptor):
                    issues.append(f"{label}：后端找不到输入图片，请上传图片或使用不依赖参考图的工作流")
            if issues:
                return {"ok": False, "message": self._redact("只读预检失败：" + "；".join(issues[:10]))}
            return {"ok": True, "message": "ComfyUI 连接及只读预检通过；未提交生图，正式执行仍需通过后端及自定义节点校验。"}
        except BackendError as error:
            return {"ok": False, "message": self._redact(error)}

    async def submit(self, plan: dict, request_id: str) -> str:
        if not isinstance(plan, dict) or any(not isinstance(plan.get(k), str) for k in ("positive", "negative")):
            raise BackendError("Generation plan requires positive and negative strings")
        if not isinstance(plan.get("seed"), int) or isinstance(plan["seed"], bool) or not 0 <= plan["seed"] <= 2**64 - 1:
            raise BackendError("Generation seed must be an unsigned 64-bit integer")
        if plan["negative"] and "negative" not in self.config["bindings"]:
            raise BackendError("该工作流没有绑定负向提示词输入，请清空负向提示词或先完成绑定。")
        request_id = _string(request_id, "request_id")
        if self._events_request_id != request_id:
            await self.stop_events()
            self._set_event_request(request_id)
        workflow = copy.deepcopy(self.config["workflow"])
        for role, binding in self.config["bindings"].items():
            workflow[binding["node_id"]]["inputs"][binding["input"]] = plan[role]
        response = await self._json("POST", "/prompt", payload={"prompt": workflow, "client_id": self._events_client_id,
                                    "extra_data": {"pictide_request_id": request_id}}, uncertain=True)
        prompt_id = response.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise BackendError("ComfyUI did not return a prompt ID; submission outcome is unknown", uncertain=True)
        self._events_prompt_id = prompt_id
        return prompt_id

    async def inspect(self, prompt_id: str) -> dict:
        prompt_id = _string(prompt_id, "prompt_id")
        history = await self._json("GET", "/history/" + quote(prompt_id, safe=""))
        item = history.get(prompt_id)
        if isinstance(item, dict):
            status = item.get("status", {})
            if not isinstance(status, dict):
                status = {}
            messages = status.get("messages", [])
            failed = status.get("status_str") == "error"
            if isinstance(messages, list):
                failed = failed or any(isinstance(x, list) and x and x[0] in {"execution_error", "execution_interrupted"} for x in messages)
            if failed:
                return {"state": "failed", "outputs": [], "error": "ComfyUI execution failed or was interrupted"}
            if status.get("completed") is True and status.get("status_str") == "success":
                outputs = []
                raw_outputs = item.get("outputs", {})
                if not isinstance(raw_outputs, dict):
                    raw_outputs = {}
                selected = self.config["output_nodes"]
                for node_id, node_output in raw_outputs.items():
                    if selected and node_id not in selected or not isinstance(node_output, dict):
                        continue
                    images = node_output.get("images", [])
                    if not isinstance(images, list):
                        continue
                    for index, raw in enumerate(images):
                        try:
                            descriptor = _safe_descriptor(raw)
                        except BackendError:
                            continue
                        outputs.append({"node_id": node_id, "index": index, **descriptor})
                return {"state": "completed", "outputs": outputs}
        queue = await self._json("GET", "/queue")
        for key, state in (("queue_running", "running"), ("queue_pending", "queued")):
            if any(isinstance(x, list) and len(x) > 1 and x[1] == prompt_id for x in self._queue_items(queue, key)):
                return {"state": state, "outputs": []}
        return {"state": "unknown", "outputs": []}

    async def reconcile(self, request_id: str) -> str | None:
        request_id = _string(request_id, "request_id")
        queue = await self._json("GET", "/queue")
        for key in ("queue_running", "queue_pending"):
            for item in self._queue_items(queue, key):
                found = self._matching_prompt(item, request_id)
                if found:
                    return found
        history = await self._json("GET", "/history", params={"max_items": HISTORY_LIMIT})
        for item in list(history.values())[-HISTORY_LIMIT:]:
            if isinstance(item, dict):
                found = self._matching_prompt(item.get("prompt"), request_id)
                if found:
                    return found
        return None

    @staticmethod
    def _queue_items(queue, key):
        items = queue.get(key, [])
        return items if isinstance(items, list) else []

    @staticmethod
    def _matching_prompt(item, request_id):
        if isinstance(item, list) and len(item) > 3 and isinstance(item[1], str) and isinstance(item[3], dict):
            if item[3].get("pictide_request_id") == request_id:
                return item[1]
        return None

    async def cancel(self, prompt_id: str) -> bool:
        prompt_id = _string(prompt_id, "prompt_id")
        queue = await self._json("GET", "/queue")
        # Never issue /interrupt: it can affect another user's running work.
        for item in self._queue_items(queue, "queue_pending"):
            if isinstance(item, list) and len(item) > 3 and item[1] == prompt_id and isinstance(item[3], dict) and item[3].get("pictide_request_id"):
                await self._json("POST", "/queue", payload={"delete": [prompt_id]}, allow_empty=True)
                # Deletion may race with the GPU taking this pending item.
                # Only release the Pictide slot after it is absent from queue.
                remaining = await self._json("GET", "/queue")
                return not any(isinstance(x, list) and len(x) > 1 and x[1] == prompt_id
                               for key in ("queue_running", "queue_pending") for x in self._queue_items(remaining, key))
        return False

    async def image(self, output: dict) -> tuple[bytes, str]:
        descriptor = _safe_descriptor(output)
        try:
            async with self.session.get(self.config["base_url"] + "/view", params=descriptor,
                                        headers=self._headers(), allow_redirects=False,
                                        timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    raise BackendError(f"ComfyUI image unavailable (HTTP {response.status})")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if content_type not in {"image/png", "image/jpeg", "image/webp", "image/gif", "image/avif"}:
                    raise BackendError("ComfyUI returned an unsupported image content type")
                if response.content_length and response.content_length > MAX_IMAGE_BYTES:
                    raise BackendError("Image exceeds the 32 MB limit")
                result = bytearray()
                async for part in response.content.iter_chunked(64 * 1024):
                    result.extend(part)
                    if len(result) > MAX_IMAGE_BYTES:
                        raise BackendError("Image exceeds the 32 MB limit")
                return bytes(result), content_type
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            raise BackendError("Cannot retrieve image from ComfyUI") from None
