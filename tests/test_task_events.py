"""Task event integration smokes using real HTTP/WS and isolated SQLite/files."""
import asyncio
import base64
from pathlib import Path
import tempfile
import time
import unittest

import aiohttp
from aiohttp import web

from backend.generation import create_backend
from backend.paths import DataPaths
from backend.task.service import JobService
from test_backend import config
from test_job_worker import RecordingRepository

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')


class TaskEventSmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.paths = DataPaths(self.directory.name).ensure()
        self.repo = RecordingRepository(self.paths.database)
        self.completed = asyncio.Queue()
        loop = asyncio.get_running_loop()
        complete = self.repo.complete
        def completed(iid, outputs):
            result = complete(iid, outputs)
            loop.call_soon_threadsafe(self.completed.put_nowait, iid)
            return result
        self.repo.complete = completed
        self.sockets = {}
        self.client_ids = {}
        self.submitted = asyncio.Queue()
        self.inspected = asyncio.Queue()
        self.history = {}
        self.submissions = []
        self.inspections = []
        self.adapters = []
        self.ws_available = True
        self.hold_first_inspect = False
        self.release_inspect = asyncio.Event()
        app = web.Application()
        app.router.add_get('/ws', self.connect)
        app.router.add_post('/prompt', self.submit)
        app.router.add_get('/history/{prompt_id}', self.get_history)
        app.router.add_get('/queue', self.queue)
        app.router.add_get('/view', self.view)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.session = aiohttp.ClientSession()
        self.repo.save_backend(config(f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'))
        def factory(source, session):
            adapter = create_backend(source, session)
            self.adapters.append(adapter)
            return adapter
        self.worker = JobService(self.repo, self.session, factory, self.paths)

    async def asyncTearDown(self):
        self.release_inspect.set()
        await self.worker.stop()
        await self.session.close()
        await self.runner.cleanup()
        self.directory.cleanup()

    def create(self, request_id):
        return self.repo.create_job(dict(backend_id='local', request_id=request_id,
                                        positive='sky, landscape', negative='text', seed=17))

    async def connect(self, request):
        if not self.ws_available:
            return web.Response(status=404)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets[request.query['clientId']] = ws
        async for _ in ws:
            pass
        return ws

    async def submit(self, request):
        body = await request.json()
        iid = body['extra_data']['pictide_request_id']
        if self.ws_available:
            self.assertIn(body['client_id'], self.sockets)
        self.client_ids[iid] = body['client_id']
        self.submissions.append(iid)
        self.submitted.put_nowait(iid)
        return web.json_response({'prompt_id': iid})

    async def get_history(self, request):
        iid = request.match_info['prompt_id']
        self._inspecting = iid
        snapshot = self.history.get(iid)
        self.inspections.append(iid)
        if snapshot:
            self.inspected.put_nowait(iid)
        return web.json_response({iid: snapshot} if snapshot else {})

    async def queue(self, request):
        # Complete while an already captured running response is in flight.
        snapshot = {'queue_running': [[0, iid, {}, {}]
                    for iid in self.submissions if iid not in self.history], 'queue_pending': []}
        self.inspected.put_nowait(self._inspecting)
        if self.hold_first_inspect:
            self.hold_first_inspect = False
            await self.release_inspect.wait()
        return web.json_response(snapshot)

    async def view(self, request):
        return web.Response(body=PNG, content_type='image/png')

    async def finish(self, iid, notify=True):
        self.history[iid] = {'status': {'completed': True, 'status_str': 'success'},
                             'outputs': {'4': {'images': [{'filename': 'image.png', 'subfolder': '', 'type': 'output'}]}}}
        if notify:
            ws = self.sockets[self.client_ids[iid]]
            for kind in ('execution_success', 'executing', 'execution_success'):
                await ws.send_json({'type': kind, 'data': {'prompt_id': iid, 'node': None}})

    async def test_event_during_inspect_saves_once_and_hands_off_without_poll_delay(self):
        first = self.create('first')
        self.create('second')
        self.create('third')
        self.hold_first_inspect = True
        await self.worker.start()
        self.assertEqual(await asyncio.wait_for(self.submitted.get(), 1), 'first')
        self.assertEqual(await asyncio.wait_for(self.submitted.get(), 1), 'second')
        await asyncio.wait_for(self.inspected.get(), 1)
        await asyncio.wait_for(self.inspected.get(), 1)
        began = time.perf_counter()
        await self.finish('first')
        self.release_inspect.set()
        self.assertEqual(await asyncio.wait_for(self.submitted.get(), 1), 'third')
        self.assertEqual(await asyncio.wait_for(self.completed.get(), 1), first['id'])
        elapsed = time.perf_counter() - began
        self.assertLess(elapsed, 1)
        self.assertEqual(self.repo.job(first['id'])['status'], 'completed')
        self.assertEqual(len(list(self.paths.images.glob('*.png'))), 1)
        self.assertEqual(len(list(self.paths.images.glob('*.json'))), 1)
        self.assertEqual(self.submissions, ['first', 'second', 'third'])
        while True:
            try:
                await asyncio.wait_for(self.inspected.get(), .1)
            except asyncio.TimeoutError:
                break
        self.assertEqual(self.worker._wait_timeout(), 30)
        before = len(self.inspections)
        ws = self.sockets[self.client_ids['second']]
        await ws.send_json({'type': 'progress', 'data': {'prompt_id': 'second', 'value': 1}})
        await ws.send_json({'type': 'execution_success', 'data': {'prompt_id': 'first'}})
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.inspected.get(), .1)
        self.assertEqual(len(self.inspections), before)
        print(f'event-to-next-submit={elapsed * 1000:.1f}ms; inspections={self.inspections}')
        await self.worker.stop()
        self.assertTrue(all(not adapter.events_connected for adapter in self.adapters))
        self.assertFalse(self.session.closed)

    async def test_disconnect_wakes_http_verification_and_releases_subscription(self):
        first = self.create('disconnected')
        await self.worker.start()
        await asyncio.wait_for(self.submitted.get(), 1)
        await asyncio.wait_for(self.inspected.get(), 1)
        self.create('next')
        await self.finish('disconnected', notify=False)
        await self.sockets[self.client_ids['disconnected']].close()
        self.assertEqual(await asyncio.wait_for(self.submitted.get(), 1), 'next')
        self.assertEqual(await asyncio.wait_for(self.completed.get(), 1), first['id'])
        self.assertEqual(self.repo.job(first['id'])['status'], 'completed')
        self.assertEqual(self.submissions.count('disconnected'), 1)
        self.assertFalse(self.adapters[0].events_connected)

    async def test_unavailable_ws_and_restored_job_keep_http_polling(self):
        self.ws_available = False
        first = self.create('polling')
        await self.worker.start()
        await asyncio.wait_for(self.submitted.get(), 1)
        await asyncio.wait_for(self.inspected.get(), 1)
        await self.finish('polling', notify=False)
        self.assertEqual(self.worker._wait_timeout(), 2)
        await asyncio.wait_for(self.inspected.get(), 2.7)
        self.assertEqual(await asyncio.wait_for(self.completed.get(), 1), first['id'])
        await self.worker.stop()
        self.assertEqual(self.repo.job(first['id'])['status'], 'completed')
        self.assertEqual(self.submissions, ['polling'])
        self.ws_available = True
        restored = self.create('restored')
        self.repo.attach_prompt(restored['id'], 'restored')
        self.repo.update_job(restored['id'], 'running')
        self.submissions.append('restored')  # backend already accepted before restart
        # Clear notices left by first job before restarting the worker.
        while not self.inspected.empty():
            self.inspected.get_nowait()
        await self.worker.start()
        self.assertEqual(await asyncio.wait_for(self.inspected.get(), 1), 'restored')
        self.assertEqual(self.worker._wait_timeout(), 2)
        self.assertFalse(self.adapters[-1].events_connected)
        await self.finish('restored', notify=False)
        await asyncio.wait_for(self.inspected.get(), 2.7)
        self.assertEqual(await asyncio.wait_for(self.completed.get(), 1), restored['id'])
        await self.worker.stop()
        self.assertEqual(self.repo.job(restored['id'])['status'], 'completed')
        self.assertEqual(self.submissions.count('restored'), 1)
