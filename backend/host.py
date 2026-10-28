"""HTTP, event transport and process lifecycle. Use cases live in application.py."""
import argparse
import asyncio
import sys
import webbrowser
import ipaddress
import json
import math
import logging
import os
import socket
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, TCPConnector, web

from .application import PictideApplication
from .candidate import CandidateService
from .store.candidate import SQLiteCandidateStore
from .store.candidate_libraries import CandidateLibraries, MAX_LIBRARY_BYTES
from .domain import BackendError, ConflictError, GoneError, NotFoundError, ValidationError
from .generation import create_backend
from .paths import DataPaths
from .recommendation.service import RecommendationService
from .recommendation.encoder import MiniLMEncoder
from .store.recommendation import SQLiteRecommendationStore
from .store import Repository
from .store.cleanup import LazyCleanup
from .store.general_settings import GeneralSettings
from .store.history_settings import HistorySettings
from .store.roam_settings import RoamSettings
from .store.workflow_library import WorkflowLibrary, MAX_BYTES
from .task import JobService
from . import __version__
from .runtime_logging import capture_exceptions
from .network import tls_context

STATIC = Path(__file__).resolve().parent.parent / "web" / "dist"
APPLICATION = web.AppKey("application", PictideApplication)
LOCAL_GENERATION = web.AppKey("local_generation", object)
ALLOW_LAN = web.AppKey("allow_lan", bool)
UPDATE_START = web.AppKey("update_start", dict)
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
            library_upload = request.path == "/api/candidate/library" and request.method == "POST"
            expected_type = "multipart/form-data" if library_upload else "application/json"
            if request.content_type != expected_type:
                raise web.HTTPUnsupportedMediaType(text=f"请求需要 {expected_type}。")
        application = request.app.get(APPLICATION)
        update_route = request.path.startswith('/api/updates')
        if application and request.path.startswith('/api/'):
            if application.update_installing and request.path != '/api/updates':
                raise web.HTTPServiceUnavailable(text='Pictide is installing an update')
        writing = application and request.path.startswith('/api/') and not update_route and request.method not in ('GET', 'HEAD')
        if writing:
            application.active_writes += 1
        try:
            response = await handler(request)
        finally:
            if writing:
                application.active_writes -= 1
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


async def liked_ranked(request):
    return web.json_response(await request.app[APPLICATION].liked_ranked(tuple(request.query.getall("tag", []))))


async def refresh_liked_ranked(request):
    payload = await body(request)
    if set(payload) != {"tags"} or not isinstance(payload["tags"], list) or any(not isinstance(tag, str) or not tag for tag in payload["tags"]):
        raise ValidationError("需要有效的 tags 标签列表。")
    return web.json_response(await request.app[APPLICATION].liked_ranked(tuple(payload["tags"]), refresh=True))


async def liked_tags(request):
    return web.json_response(await request.app[APPLICATION].liked_tags())


async def feedback(request):
    return web.json_response(await request.app[APPLICATION].feedback(request.match_info["id"], await body(request)))


async def clear_generated(request):
    return web.json_response(await request.app[APPLICATION].clear_generated(
        request.match_info.get("id"), await body(request)))


async def prompt_settings(request):
    return web.json_response(await request.app[APPLICATION].prompt_settings(
        await body(request) if request.method == "PUT" else None))


async def canvas_pools(request):
    application = request.app[APPLICATION]
    if request.method == 'PUT':
        result = await application.save_canvas_pool(request.match_info['id'], await body(request))
    elif request.method == 'DELETE':
        result = await application.delete_canvas_pool(request.match_info['id'])
    else:
        result = await application.list_canvas_pools()
    return web.json_response(result)


async def llm_connections(request):
    application = request.app[APPLICATION]
    identifier = request.match_info.get('id')
    if request.method == 'PUT':
        result = await application.save_llm(identifier, await body(request))
    elif request.method == 'DELETE':
        result = await application.delete_llm(identifier)
    else:
        result = await application.llm_connections()
    return web.json_response(result)


async def llm_action(request):
    operation = request.match_info.get('operation', 'status')
    if operation == 'sign-in':
        # The OAuth loopback callback must return to the computer running Pictide.
        if request.remote not in ('127.0.0.1', '::1') or urlsplit('http://' + request.host).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValidationError('Open Pictide on the server computer using its localhost address to sign in to ChatGPT.')
    return web.json_response(await request.app[APPLICATION].llm_action(request.match_info['id'], operation))


async def general_settings(request):
    return web.json_response(await request.app[APPLICATION].general_settings(
        await body(request) if request.method == "PUT" else None))


def local_generation_access(request):
    try:
        return (ipaddress.ip_address(request.remote or '').is_loopback and
                urlsplit('http://' + request.host).hostname in ('127.0.0.1', 'localhost', '::1'))
    except ValueError:
        return False


async def local_generation_settings(request):
    if not local_generation_access(request):
        if request.method == 'GET':
            return web.json_response({'can_configure': False})
        raise web.HTTPForbidden(text='Configure local ComfyUI on the Pictide computer using localhost.')
    service = request.app[LOCAL_GENERATION]
    if request.method == 'PUT':
        result = await asyncio.to_thread(service.save, await body(request))
        request.app[APPLICATION].events.publish('local_generation')
    else:
        result = await asyncio.to_thread(service.settings)
    return web.json_response(result)


async def local_generation_detect(request):
    if not local_generation_access(request):
        raise web.HTTPForbidden(text='Detect local ComfyUI on the Pictide computer using localhost.')
    return web.json_response(await asyncio.to_thread(request.app[LOCAL_GENERATION].detect, await body(request)))


async def history_settings(request):
    return web.json_response(await request.app[APPLICATION].history_settings(
        await body(request) if request.method == "PUT" else None))


async def roam_settings(request):
    return web.json_response(await request.app[APPLICATION].roam_settings(
        await body(request) if request.method == "PUT" else None))


async def preferences(request):
    if set(request.query) - {"page", "all"}:
        raise ValidationError("偏好查看只接受 page 和 all 参数。")
    if request.query.get("all", "0") not in {"0", "1"}:
        raise ValidationError("all 参数须为 0 或 1。")
    return web.json_response(await request.app[APPLICATION].preferences(
        request.query.get("page", "1"), all_terms=request.query.get("all") == "1"))


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


async def candidate_library(request):
    application = request.app[APPLICATION]
    if request.method == "GET":
        return web.json_response(await application.candidate_library("list"))
    if request.method == "PUT":
        return web.json_response(await application.candidate_library("select", await body(request)))
    path = None
    try:
        reader = await request.multipart()
        part = await reader.next()
        if part is None or part.name != "file" or not part.filename:
            raise ValidationError("请选择词库文件上传。")
        with tempfile.NamedTemporaryFile(dir=application.paths.tmp, suffix=".upload", delete=False) as target:
            path = Path(target.name)
            total = 0
            while chunk := await part.read_chunk(1024 * 1024):
                total += len(chunk)
                if total > MAX_LIBRARY_BYTES:
                    raise ValidationError("词库上传最大支持 2 GiB。")
                target.write(chunk)
        result = await application.candidate_library("add", upload_path=path, filename=part.filename)
        return web.json_response(result, status=201)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


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
    async with ClientSession(timeout=ClientTimeout(total=25), trust_env=False,
                             connector=TCPConnector(ssl=tls_context())) as session:
        managed = app.get(LOCAL_GENERATION)
        try:
            if managed is not None:
                await asyncio.to_thread(managed.start)
                await managed.configure(app[APPLICATION], session)
            await app[APPLICATION].start(session)
            try:
                yield
            finally:
                await app[APPLICATION].stop()
                await app[APPLICATION].updates.close()
        finally:
            if managed is not None:
                await asyncio.to_thread(managed.close)


async def shutdown(app):
    app[APPLICATION].events.close()


def stop_for_update():
    from .desktop.launcher import notify_launcher
    notify_launcher('updating')
    raise web.GracefulExit()


def update_status(request):
    result = request.app[APPLICATION].updates.status()
    if not request.remote or not ipaddress.ip_address(request.remote).is_loopback:
        result.update(can_download=False, can_install=False, reason='local_access_required')
    return result


async def updates(request):
    return web.json_response(update_status(request))


async def update_action(request):
    application = request.app[APPLICATION]
    operation = request.match_info['operation']
    payload = await body(request)
    if payload and (operation != 'install' or set(payload) != {'initiator_pid'} or type(payload['initiator_pid']) is not int or payload['initiator_pid'] <= 0):
        raise ValidationError('Update actions do not accept download URLs or installation paths')
    if operation in {'download', 'install'} and (not request.remote or not ipaddress.ip_address(request.remote).is_loopback):
        raise web.HTTPForbidden(text='Install updates from this computer using its localhost address')
    if operation == 'check':
        await application.updates.check()
    elif operation == 'download':
        application.updates.start_download()
    elif operation == 'install':
        from .updates.apply import launch_helper
        start = request.app.get(UPDATE_START)
        if not start:
            raise ValidationError('This instance cannot restart itself')
        pids = start['pids'] + ([payload['initiator_pid']] if payload else [])
        path, program = await application.prepare_update(start['arguments'], pids)
        try:
            await asyncio.to_thread(launch_helper, path, program)
        except Exception as error:
            application.update_installing = False
            application.updates.publish(phase='ready', error=str(error))
            raise
        application.updates.publish(phase='installing')
        asyncio.get_running_loop().call_later(.5, stop_for_update)
    else:
        raise web.HTTPNotFound()
    return web.json_response(update_status(request))


def create_app(data_dir=None, backend_factory=create_backend, *, allow_lan=False):
    """Composition root: adapters are assembled here, outside request handlers."""
    app = web.Application(middlewares=[boundary], client_max_size=MAX_BYTES)
    app[ALLOW_LAN] = allow_lan
    paths = DataPaths(data_dir).ensure()
    libraries = CandidateLibraries(paths)
    candidate_store = SQLiteCandidateStore(paths.candidate_database, libraries.selected_path())
    storage = Repository(paths.database)
    recommendation_store = SQLiteRecommendationStore(storage)
    recommendation = RecommendationService(recommendation_store, MiniLMEncoder(paths.models / "minilm"))
    tasks = JobService(storage, None, backend_factory, paths=paths)
    history = HistorySettings(paths)
    roam = RoamSettings(paths)
    app[APPLICATION] = PictideApplication(paths, storage, tasks,
        CandidateService(candidate_store, libraries), recommendation,
        history, LazyCleanup(storage, paths, history.retention, max_roam_history=roam.history_limit),
        WorkflowLibrary(paths.workflows, tasks.connections.validate), roam, recommendation_store, GeneralSettings(paths))
    from .prompt_preparation import PromptPreparation
    from .store.prompting import PromptStore
    from .store.canvas_pools import CanvasPoolStore
    from .store.chatgpt import ChatGPTCredentials
    from .prompting.chatgpt import ChatGPTClient
    app[APPLICATION].chatgpt = ChatGPTClient(ChatGPTCredentials(paths.root), app[APPLICATION].llm_changed)
    app[APPLICATION].canvas_pools = CanvasPoolStore(storage)
    app[APPLICATION].prompting = PromptPreparation(PromptStore(storage), app[APPLICATION].chatgpt)
    from .updates.service import UpdateService
    application = app[APPLICATION]
    application.updates = UpdateService(paths, on_change=lambda: application.events.publish('updates'))
    from .setup.comfy_lifecycle import LocalComfyLifecycle
    app[LOCAL_GENERATION] = LocalComfyLifecycle(paths, storage.backend, storage.backends)
    app.cleanup_ctx.append(lifecycle)
    app.on_shutdown.append(shutdown)
    app.add_routes([
        web.get("/api/bootstrap", bootstrap), web.get("/api/events", events),
        web.get('/api/updates', updates), web.post('/api/updates/{operation:check|download|install}', update_action),
        web.get("/api/settings/prompting", prompt_settings), web.put("/api/settings/prompting", prompt_settings),
        web.get('/api/canvas-pools', canvas_pools), web.put('/api/canvas-pools/{id}', canvas_pools),
        web.delete('/api/canvas-pools/{id}', canvas_pools),
        web.get('/api/llm-apis', llm_connections), web.put('/api/llm-apis/{id}', llm_connections),
        web.delete('/api/llm-apis/{id}', llm_connections),
        web.get('/api/llm-apis/{id}/status', llm_action, name='llm-status'),
        web.post('/api/llm-apis/{id}/{operation:sign-in|cancel|models|disconnect|welcome}', llm_action),
        web.get("/api/settings/general", general_settings), web.put("/api/settings/general", general_settings),
        web.get('/api/settings/local-generation', local_generation_settings),
        web.put('/api/settings/local-generation', local_generation_settings),
        web.post('/api/settings/local-generation/detect', local_generation_detect),
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
        web.get("/api/liked/ranked", liked_ranked),
        web.post("/api/liked/ranked/refresh", refresh_liked_ranked),
        web.get("/api/artifacts/{id}/preference-score", preference_score),
        web.get("/api/artifacts", artifacts), web.put("/api/artifacts/{id}/feedback", feedback),
        web.delete("/api/generated", clear_generated), web.delete("/api/generated/{id}", clear_generated),
        web.get("/api/artifacts/{id}/image", image), web.get("/api/artifacts/{id}/prompts", prompts),
        web.get("/api/candidate/library", candidate_library),
        web.post("/api/candidate/library", candidate_library),
        web.put("/api/candidate/library", candidate_library),
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


async def open_browser_when_ready(url, on_ready=None):
    """Open the default browser only after the listening service answers bootstrap."""
    async with ClientSession(timeout=ClientTimeout(total=2)) as session:
        for _ in range(30):
            ready = False
            try:
                async with session.get(url + "/api/bootstrap") as response:
                    ready = response.status == 200
            except (OSError, asyncio.TimeoutError):
                pass
            if ready:
                if on_ready is not None and await on_ready() is False:
                    return
                try:
                    await asyncio.to_thread(webbrowser.open, url)
                except webbrowser.Error:
                    from .desktop.terminal import status
                    from .desktop.text import translate
                    status(translate('local_address', address=url), heading=translate('ready'))
                return
            await asyncio.sleep(0.1)


def main(argv=None):
    with capture_exceptions():
        return _main(argv)


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Pictide")
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost", "::1", "0.0.0.0"])
    parser.add_argument("--port", type=int, default=8189)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--vocabulary", choices=['filtered', 'all-ratings'], default=None,
                        help="Vocabulary to download when none is valid; non-interactive default: filtered. "
                             "all-ratings may generate explicit content.")
    parser.add_argument("--lan", action="store_true", help="Allow devices on the local network")
    parser.add_argument("--no-browser", action="store_true", help="Keep the browser closed")
    parser.add_argument("--desktop", action="store_true", help="Use the Windows desktop tray")
    parser.add_argument("--cli", action="store_true", help="Keep the terminal and disable desktop integration")
    parser.add_argument("--setup", action="store_true", help="Open Windows local generation setup")
    parser.add_argument("--desktop-worker", action="store_true", help=argparse.SUPPRESS)
    updating = parser.add_mutually_exclusive_group()
    updating.add_argument('--check-updates', action='store_true', help='Check the latest stable release without downloading or installing')
    updating.add_argument('--update', action='store_true', help='Explicitly download and install a compatible stable release')
    updating.add_argument('--apply-update', metavar='PLAN', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.apply_update:
        from .updates.apply import apply_plan
        apply_plan(args.apply_update)
        return
    if args.check_updates or args.update:
        from .update_cli import run
        raise SystemExit(asyncio.run(run(args)))
    frozen = getattr(sys, "frozen", False)
    if args.setup and sys.platform != 'win32':
        parser.error('--setup is available on Windows')
    desktop_requested = args.desktop and sys.platform == 'win32' and not (args.cli or args.no_browser)
    if args.desktop_worker:
        if sys.platform == 'darwin' and os.environ.get('PICTIDE_DESKTOP_PARENT_PIPE') == '1':
            from .desktop.launcher import watch_desktop_parent
            watch_desktop_parent()
        # Frozen console programs ignore PYTHONIOENCODING; use UTF-8 for the startup log.
        for stream in (sys.stdout, sys.stderr):
            if stream is not None:
                stream.reconfigure(encoding='utf-8', errors='replace')
    interactive_setup = sys.platform == 'win32' and not args.desktop_worker and (args.setup or desktop_requested)
    try:
        paths = DataPaths(args.data_dir)
        if interactive_setup:
            from .setup.local_generation_session import prepare_windows_data_directory, prepare_windows_setup
            paths = prepare_windows_data_directory(paths, force=args.setup)
            if paths is None:
                return
        paths.configure_runtime()
        if interactive_setup:
            if not prepare_windows_setup(paths, force=args.setup):
                return
    except (OSError, ValueError, RuntimeError) as error:
        logging.getLogger('backend').exception('Runtime preparation failed')
        from .desktop.text import translate
        from .desktop.terminal import status, close_prompt
        status(str(error), heading=translate('terminal_error'), stream=sys.stderr)
        close_prompt(str(error))
        raise SystemExit(1) from None
    if desktop_requested and not args.desktop_worker:
        from .desktop.launcher import launch_desktop
        from .setup.vocabulary import choose_vocabulary
        arguments = list(sys.argv[1:] if argv is None else argv)
        try:
            if args.vocabulary is None:
                args.vocabulary = choose_vocabulary(paths, interactive=bool(sys.stdin and sys.stdin.isatty()
                                                                            and sys.stdout and sys.stdout.isatty()))
                if args.vocabulary:
                    arguments += ['--vocabulary', args.vocabulary]
            if launch_desktop(arguments, paths):
                return
        except (EOFError, KeyboardInterrupt):
            return
        # The worker released its tray-less session; this terminal now owns logs.
        paths.configure_runtime()
    host = "0.0.0.0" if args.lan else args.host
    url_host = "[::1]" if host == "::1" else "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{url_host}:{args.port}"
    desktop = None
    worker_socket = None
    started = time.monotonic()
    logger = logging.getLogger('backend')
    instance = None
    if desktop_requested:
        from .desktop.session import DesktopSession, announce
        desktop = DesktopSession(paths, url)
    try:
        if desktop is not None:
            if not desktop.claim():
                return
        logger.info('Starting Pictide version=%s pid=%s data_directory=%s host=%s port=%s mode=%s',
                    __version__, os.getpid(), paths.root, host, args.port,
                    'desktop-worker' if args.desktop_worker else 'desktop' if desktop else 'cli')
        if desktop is not None:
            desktop.reserve(host, args.port)
            announce('starting')
            announce('data_directory', directory=paths.root)
        if sys.platform == 'darwin' and args.desktop_worker:
            from .desktop.launcher import reserve_desktop_socket
            worker_socket = reserve_desktop_socket(host, args.port)
        PictideApplication.prepare_startup(paths, vocabulary=args.vocabulary,
            interactive=bool(not args.desktop_worker and sys.stdin and sys.stdin.isatty()
                             and sys.stdout and sys.stdout.isatty()))
        app = create_app(paths.root, allow_lan=host == "0.0.0.0")
        from .updates.runtime import save_instance, ready_instance, remove_instance
        arguments = json.loads(os.environ.get('PICTIDE_DESKTOP_ARGUMENTS', 'null'))
        # Finder launches have an empty argument list; worker CLI flags must not replace it.
        if arguments is None:
            arguments = list(sys.argv[1:] if argv is None else argv)
        arguments = [value for value in arguments if value not in ('--desktop-worker', '--setup')]
        # The macOS parent supplies its own original arguments instead of worker-only flags.
        pids = [os.getpid()]
        if os.environ.get('PICTIDE_DESKTOP_PARENT_PID'):
            pids.append(int(os.environ['PICTIDE_DESKTOP_PARENT_PID']))
        if '--data-dir' not in arguments:
            arguments += ['--data-dir', str(paths.root)]
        app[UPDATE_START] = dict(arguments=arguments, pids=pids)
        instance = save_instance(paths, url, arguments, app[APPLICATION].updates.installation)
        async def log_ready(app):
            ready_instance(paths, instance)
            addresses = []
            if host == '0.0.0.0':
                try:
                    addresses = [f'http://{address}:{args.port}' for address in
                                 sorted(set(socket.gethostbyname_ex(socket.gethostname())[2]))
                                 if not address.startswith('127.') and address != '0.0.0.0']
                except OSError:
                    logger.warning('Could not discover LAN addresses', exc_info=True)
            logger.info('Pictide ready local=%s lan=%s startup_seconds=%.3f', url,
                        ','.join(addresses) or '-', time.monotonic() - started)
            from .desktop.terminal import Console
            from .desktop.text import translate
            Console().show(translate('ready'),
                [translate('local_address', address=url),
                 *[translate('lan_address', address=address) for address in addresses],
                 translate('data_directory', directory=paths.root),
                 translate('startup_log', path=paths.logs / 'pictide.log')])
        app.on_startup.append(log_ready)
        if worker_socket is not None:
            async def notify_worker_ready(app):
                from .desktop.launcher import notify_launcher
                notify_launcher('ready')
            app.on_startup.append(notify_worker_ready)
        if (desktop is not None or frozen) and not (args.no_browser or args.cli):
            browser_task = None
            async def launch_browser(app):
                nonlocal browser_task
                browser_task = asyncio.create_task(open_browser_when_ready(url, desktop.ready if desktop else None))
            async def stop_browser(app):
                if browser_task is not None:
                    browser_task.cancel()
                    await asyncio.gather(browser_task, return_exceptions=True)
            app.on_startup.append(launch_browser)
            app.on_shutdown.append(stop_browser)
        if desktop is not None:
            web.run_app(app, sock=desktop.socket, access_log=None, print=None)
        elif worker_socket is not None:
            web.run_app(app, sock=worker_socket, access_log=None, print=None)
        else:
            web.run_app(app, host=host, port=args.port, access_log=None, print=None)
    except KeyboardInterrupt:
        logger.info('Pictide startup cancelled')
    except Exception as error:
        from .desktop.text import translate
        logging.getLogger('backend').exception('Pictide startup failed')
        from .desktop.terminal import status, close_prompt
        message = translate('startup_failed', error=error)
        status(message, heading=translate('terminal_error'), stream=sys.stderr)
        if desktop is not None and not os.environ.get('PICTIDE_DESKTOP_STATUS') and sys.stdin is not None and sys.stdin.isatty():
            close_prompt(message)
        raise SystemExit(1) from None
    finally:
        if instance is not None:
            remove_instance(paths, instance)
        if worker_socket is not None:
            worker_socket.close()
        if desktop is not None:
            desktop.close()
        logger.info('Pictide stopped elapsed_seconds=%.3f', time.monotonic() - started)


if __name__ == "__main__":
    main()
