"""Isolated ComfyUI event protocol smokes; no generation server or GPU needed."""
import asyncio
import unittest

import aiohttp
from aiohttp import web

from backend.generation.comfyui import ComfyBackend
from tests.test_backend import config


class ComfyEventTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clients = []
        self.sockets = []
        self.notices = asyncio.Queue()
        self.submissions = []
        self.emit_early = False
        self.ws_available = True
        app = web.Application()
        app.router.add_get('/ws', self.connect)
        app.router.add_post('/prompt', self.submit)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.session = aiohttp.ClientSession()
        self.adapter = ComfyBackend(config(f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'), self.session)

    async def asyncTearDown(self):
        await self.adapter.stop_events()
        await self.session.close()
        await self.runner.cleanup()

    def notify(self):
        self.notices.put_nowait(True)

    async def connect(self, request):
        if not self.ws_available:
            return web.Response(status=404)
        self.assertEqual(request.headers['Authorization'], 'Bearer secret-test-key')
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.clients.append(request.query['clientId'])
        self.sockets.append(ws)
        async for _ in ws:
            pass
        return ws

    async def submit(self, request):
        body = await request.json()
        self.submissions.append(body)
        if self.emit_early:
            self.assertEqual(body['client_id'], self.clients[-1])
            await self.sockets[-1].send_json({'type': 'execution_success', 'data': {'prompt_id': 'prompt-1'}})
            # Force the receiver to run before the POST response is released.
            await asyncio.wait_for(self.notices.get(), 1)
            self.early_received = True
        return web.json_response({'prompt_id': 'prompt-1'})

    async def send(self, kind, **data):
        await self.sockets[-1].send_json({'type': kind, 'data': data})

    async def test_subscribe_before_submit_and_filter_terminal_events(self):
        self.emit_early = True
        self.assertTrue(await self.adapter.start_events('request-1', self.notify))
        self.assertTrue(self.adapter.events_connected)
        self.assertEqual(await self.adapter.submit({'positive': 'sky', 'negative': '', 'seed': 1}, 'request-1'), 'prompt-1')
        self.assertTrue(self.early_received)
        self.assertEqual(self.submissions[0]['extra_data']['pictide_request_id'], 'request-1')
        await self.sockets[-1].send_bytes(b'preview')
        await self.sockets[-1].send_str('invalid json')
        await self.send('progress', prompt_id='prompt-1', value=1)
        await self.send('executing', prompt_id='prompt-1', node='4')
        await self.send('executing', prompt_id='prompt-1')
        await self.send('execution_success', prompt_id='someone-else')
        for kind in ('execution_success', 'execution_error', 'execution_interrupted', 'executing'):
            await self.send(kind, prompt_id='prompt-1', node=None)
            await asyncio.wait_for(self.notices.get(), 1)
            self.assertTrue(self.notices.empty())
        task = self.adapter._events_task
        await self.adapter.stop_events()
        self.assertTrue(task.done())
        self.assertFalse(self.adapter.events_connected)
        self.assertFalse(self.session.closed)
        self.assertTrue(self.notices.empty())

    async def test_disconnect_reconnect_keeps_prompt_filter_and_new_request_resets_it(self):
        await self.adapter.start_events('request-1', self.notify)
        await self.adapter.submit({'positive': 'sky', 'negative': '', 'seed': 1}, 'request-1')
        first_client = self.clients[-1]
        await self.sockets[-1].close()
        await asyncio.wait_for(self.notices.get(), 1)
        self.assertFalse(self.adapter.events_connected)
        self.assertTrue(await self.adapter.start_events('request-1', self.notify))
        self.assertEqual(self.clients[-1], first_client)
        await self.send('execution_success', prompt_id='someone-else')
        await self.send('execution_success', prompt_id='prompt-1')
        await asyncio.wait_for(self.notices.get(), 1)
        self.assertTrue(self.notices.empty())
        self.assertTrue(await self.adapter.start_events('request-2', self.notify))
        self.assertNotEqual(self.clients[-1], first_client)
        await self.send('execution_success', prompt_id='prompt-2')
        await asyncio.wait_for(self.notices.get(), 1)
        self.assertTrue(self.notices.empty())

    async def test_unavailable_events_do_not_prevent_http_submission(self):
        self.ws_available = False
        self.assertFalse(await self.adapter.start_events('request-1', self.notify))
        self.assertFalse(self.adapter.events_connected)
        self.assertEqual(await self.adapter.submit({'positive': 'sky', 'negative': '', 'seed': 1}, 'request-1'), 'prompt-1')
        self.assertTrue(self.submissions[0]['client_id'].startswith('pictide-'))
        self.assertTrue(self.notices.empty())
