"""HTTP, event transport and process lifecycle. Use cases live in application.py."""
import argparse
import ipaddress
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, web

from .application import PictideApplication
from .candidate import CandidateService
from .store.candidate import SQLiteCandidateStore
from .domain import BackendError, ConflictError, GoneError, NotFoundError, ValidationError
from .generation import create_backend
from .paths import DataPaths
from .recommand import RecommendationService
from .recommand.encoder import MiniLMEncoder
from .store.recommendation import SQLiteRecommendationStore
from .store import Repository
from .store.cleanup import LazyCleanup
from .store.general_settings import GeneralSettings
from .store.history_settings import HistorySettings
from .store.roam_settings import RoamSettings
from .store.workflow_library import WorkflowLibrary, MAX_BYTES
from .task import JobService

STATIC = Path(__file__).resolve().parent.parent / "web" / "dist"
APPLICATION = web.AppKey("application", PictideApplication)
ALLOW_LAN = web.AppKey("allow_lan", bool)
CSP = "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"


@web.middleware
async def boundary(request, handler):
    candidate = request.path.startswith("/api/candidate/")
    try:
        try:
            local = urlsplit("http://" + request.host).hostname
        except ValueError:
            local = None
        allowed = local in {"127.0.0.1", "localhost", "::1"}
        if not allowed and request.app.get(ALLOW_LAN, False):
            address = request.transport.get_extra_info("sockname") if request.transport else None
            if address and local == address[0]:
                allowed = ipaddress.ip_address(local).is_private
        if not allowed:
            raise web.HTTPForbidden(text="请通过本机地址访问；局域网访问需要使用局域网启动入口。")
        if request.path.startswith("/api/") and request.method not in ("GET", "HEAD"):
            origin = request.headers.get("Origin")
            if origin and origin != f"{request.scheme}://{request.host}":
                raise web.HTTPForbidden(text="不允许跨站修改本地应用。")
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                raise web.HTTPForbidden(text="不允许跨站修改本地应用。")
            if request.content_type != "application/json":
                raise web.HTTPUnsupportedMediaType(text="请求需要 application/json。")
        response = await handler(request)
    except ConflictError as exc:
        response = web.json_response({"error": str(exc)}, status=409)
    except NotFoundError as exc:
        response = web.json_response({"error": str(exc) or "记录不存在。"}, status=404)
    except GoneError as exc:
        response = web.json_response({"error": str(exc)}, status=410)
    except (ValidationError, BackendError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        data = {"error": str(exc)}
        if candidate:
            data["kind"] = "validation"
        response = web.json_response(data, status=400)
    except web.HTTPException as exc:
        response = web.Response(body=exc.body, status=exc.status, headers=exc.headers)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = CSP
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


async def body(request, limit=MAX_BYTES):
    raw = await request.read()
    if len(raw) > limit:
        raise web.HTTPRequestEntityTooLarge(max_size=limit, actual_size=len(raw))
    def constant(value):
        raise ValidationError("JSON 不允许 NaN 或 Infinity。")
    def pairs(items):
        document = {}
        for key, value in items:
            if key in document:
                raise ValidationError("JSON 不允许重复字段。")
            document[key] = value
        return document
    data = json.loads(raw.decode("utf-8-sig"), parse_constant=constant, object_pairs_hook=pairs)
    if not isinstance(data, dict):
        raise ValidationError("请求内容必须是 JSON 对象。")
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValidationError("JSON numbers must be finite")
        if isinstance(value, dict):
            for item in value.values():
                finite(item)
        elif isinstance(value, list):
            for item in value:
                finite(item)
    finite(data)
    return data


async def bootstrap(request):
    return web.json_response(await request.app[APPLICATION].bootstrap())


async def connection(request):
    action = "delete_backend" if request.method == "DELETE" else request.match_info.get("action", "save_backend")
    action = {"check": "check_backend", "template": "workflow_template"}.get(action, action)
    operation = getattr(request.app[APPLICATION], action)
    return web.json_response(await operation(request.match_info["id"], await body(request)))


async def jobs(request):
    app = request.app[APPLICATION]
    if request.method == "GET":
        if "page" in request.query:
            return web.json_response(await app.job_page(request.query["page"]))
        return web.json_response({"jobs": await app.list_jobs()})
    return web.json_response(await app.submit_job(await body(request)), status=202)


async def cancel_pending_jobs(request):
    return web.json_response(await request.app[APPLICATION].cancel_pending_jobs(await body(request)))


async def cancel_job(request):
    await body(request)
    return web.json_response(await request.app[APPLICATION].cancel_job(request.match_info["id"]))


async def artifacts(request):
    try:
        limit = int(request.query.get("limit", "200"))
    except ValueError:
        raise ValidationError("分页数量必须是整数。") from None
    return web.json_response(await request.app[APPLICATION].artifacts(
        request.query.get("liked") == "1", limit, request.query.get("before"), request.query.get("source", "all"), request.query.get("around"), tuple(request.query.getall("tag", []))))


async def preference_score(request):
    return web.json_response(await request.app[APPLICATION].preference_score(request.match_info["id"]))


async def liked_tags(request):
    return web.json_response(await request.app[APPLICATION].liked_tags())


async def feedback(request):
    return web.json_response(await request.app[APPLICATION].feedback(request.match_info["id"], await body(request)))


async def clear_generated(request):
    return web.json_response(await request.app[APPLICATION].clear_generated(
        request.match_info.get("id"), await body(request)))


async def general_settings(request):
    return web.json_response(await request.app[APPLICATION].general_settings(
        await body(request) if request.method == "PUT" else None))


async def history_settings(request):
    return web.json_response(await request.app[APPLICATION].history_settings(
        await body(request) if request.method == "PUT" else None))


async def roam_settings(request):
    return web.json_response(await request.app[APPLICATION].roam_settings(
        await body(request) if request.method == "PUT" else None))


async def preferences(request):
    if set(request.query) - {"page"}:
        raise ValidationError("偏好查看只接受 page 参数。")
    return web.json_response(await request.app[APPLICATION].preferences(request.query.get("page", "1")))


async def reset_preferences(request):
    return web.json_response(await request.app[APPLICATION].reset_preferences(await body(request, limit=2048)))


async def ensure_roam(request):
    return web.json_response(await request.app[APPLICATION].ensure_roam(await body(request)))


async def roam_view(request):
    return web.json_response(await request.app[APPLICATION].roam_view(
        await body(request) if request.method == "PUT" else None))


async def image(request):
    try:
        return web.FileResponse(await request.app[APPLICATION].image(request.match_info["id"]))
    except BackendError as exc:
        return web.json_response({"error": str(exc)}, status=502)


async def prompts(request):
    data = await request.app[APPLICATION].prompts(request.match_info["id"])
    return web.Response(text=json.dumps(data, ensure_ascii=False, indent=2), content_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{request.match_info["id"]}.json"'})


async def candidate(request):
    data = await body(request, limit=1_100_000) if request.method in ("POST", "DELETE") else None
    identifier = request.match_info.get("id")
    action = request.match_info.get("action", "presets")
    if identifier:
        action = "delete_preset" if request.method == "DELETE" else "preset"
    elif action == "presets" and request.method == "POST":
        action = "save_preset"
    return web.json_response(await request.app[APPLICATION].candidate(action, data, identifier, dict(request.query)))


async def workflows(request):
    app = request.app[APPLICATION]
    if request.method == "DELETE":
        return web.json_response(await app.delete_workflow(request.match_info["id"], await body(request)))
    if request.method == "POST":
        return web.json_response(await app.save_workflow(await body(request)), status=201)
    if "id" in request.match_info:
        return web.json_response(await app.read_workflow(request.match_info["id"]))
    return web.json_response(await app.list_workflows())


async def index(request):
    return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


async def old_editor(request):
    query = "?" + request.query_string if request.query_string else ""
    raise web.HTTPFound("/" + query + "#prompts")


async def events(request):
    response = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-store",
                                          "X-Accel-Buffering": "no", "Content-Security-Policy": CSP})
    await response.prepare(request)
    try:
        async for event in request.app[APPLICATION].events.stream():
            text = ": keep-alive\n\n" if event is None else "event: change\ndata: " + json.dumps(event) + "\n\n"
            await response.write(text.encode("utf-8"))
    except (ConnectionResetError, ConnectionError):
        pass
    return response


async def lifecycle(app):
    async with ClientSession(timeout=ClientTimeout(total=25), trust_env=False) as session:
        await app[APPLICATION].start(session)
        try:
            yield
        finally:
            await app[APPLICATION].stop()


async def shutdown(app):
    app[APPLICATION].events.close()


def create_app(data_dir=None, backend_factory=create_backend, *, allow_lan=False):
    """Composition root: adapters are assembled here, outside request handlers."""
    app = web.Application(middlewares=[boundary], client_max_size=MAX_BYTES)
    app[ALLOW_LAN] = allow_lan
    paths = DataPaths(data_dir).ensure()
    storage = Repository(paths.database)
    recommendation_store = SQLiteRecommendationStore(storage)
    recommendation = RecommendationService(recommendation_store, MiniLMEncoder(paths.cache / "embeddings"))
    tasks = JobService(storage, None, backend_factory, paths=paths)
    history = HistorySettings(paths)
    roam = RoamSettings(paths)
    app[APPLICATION] = PictideApplication(paths, storage, tasks,
        CandidateService(SQLiteCandidateStore(paths.candidate_database)), recommendation,
        history, LazyCleanup(storage, paths, history.retention, max_roam_history=roam.history_limit),
        WorkflowLibrary(paths.workflows, tasks.connections.validate), roam, recommendation_store, GeneralSettings(paths))
    app.cleanup_ctx.append(lifecycle)
    app.on_shutdown.append(shutdown)
    app.add_routes([
        web.get("/api/bootstrap", bootstrap), web.get("/api/events", events),
        web.get("/api/settings/general", general_settings), web.put("/api/settings/general", general_settings),
        web.get("/api/settings/history", history_settings), web.put("/api/settings/history", history_settings),
        web.get("/api/settings/roam", roam_settings), web.put("/api/settings/roam", roam_settings),
        web.get("/api/recommendation/preferences", preferences),
        web.post("/api/recommendation/preferences/reset", reset_preferences),
        web.post("/api/roam/ensure", ensure_roam),
        web.get("/api/roam/view", roam_view), web.put("/api/roam/view", roam_view),
        web.put("/api/backends/{id}", connection),
        web.delete("/api/backends/{id}", connection),
        web.post("/api/backends/{id}/{action:check|models|template}", connection),
        web.get("/api/jobs", jobs), web.post("/api/jobs", jobs), web.post("/api/jobs/cancel-pending", cancel_pending_jobs),
        web.post("/api/jobs/{id}/cancel", cancel_job),
        web.get("/api/liked/tags", liked_tags),
        web.get("/api/artifacts/{id}/preference-score", preference_score),
        web.get("/api/artifacts", artifacts), web.put("/api/artifacts/{id}/feedback", feedback),
        web.delete("/api/generated", clear_generated), web.delete("/api/generated/{id}", clear_generated),
        web.get("/api/artifacts/{id}/image", image), web.get("/api/artifacts/{id}/prompts", prompts),
        web.get("/api/candidate/{action:tags|presets|dataset}", candidate),
        web.get("/api/candidate/presets/{id}", candidate),
        web.post("/api/candidate/{action:presets|generate|relations}", candidate),
        web.delete("/api/candidate/presets/{id}", candidate),
        web.get("/api/workflows", workflows), web.get("/api/workflows/{id}", workflows), web.post("/api/workflows", workflows),
        web.delete("/api/workflows/{id}", workflows),
        web.get("/", index), web.get("/prompts", old_editor), web.get("/rule-prompts/editor", old_editor),
        web.static("/static/ui", STATIC, show_index=False),
    ])
    return app


def main():
    parser = argparse.ArgumentParser(description="Pictide")
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost", "::1", "0.0.0.0"])
    parser.add_argument("--port", type=int, default=8189)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    paths = DataPaths(args.data_dir).configure_runtime()
    web.run_app(create_app(paths.root, allow_lan=args.host == "0.0.0.0"), host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
