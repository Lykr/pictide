import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import ProxyHandler, build_opener

from aiohttp import ClientSession, web

from backend.events import EventHub
from backend.host import APPLICATION, boundary, network_settings
from backend.listeners import NETWORK, NetworkAccess
from tests import ROOT


class NetworkAccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = web.Application(middlewares=[boundary])
        self.app[NETWORK] = NetworkAccess()
        self.app[APPLICATION] = SimpleNamespace(update_installing=False, active_writes=0, events=EventHub())
        self.app.add_routes([web.get('/api/settings/network', network_settings),
                             web.put('/api/settings/network', network_settings)])
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        await self.app[NETWORK].start(self.runner, port=0)
        self.port = self.app[NETWORK].port
        self.local = f'http://127.0.0.1:{self.port}/api/settings/network'
        self.lan = f'http://127.0.0.2:{self.port}/api/settings/network'
        self.client = ClientSession(trust_env=False)
        self.addresses = patch('backend.listeners.lan_addresses', return_value=['127.0.0.2'])
        self.addresses.start()

    async def asyncTearDown(self):
        self.addresses.stop()
        await self.client.close()
        await self.runner.cleanup()

    async def test_enable_and_disable_keep_the_local_listener_and_application(self):
        before = self.app[APPLICATION]
        async with self.client.put(self.local, json={'enabled': True}) as response:
            self.assertEqual(response.status, 200)
            status = await response.json()
            self.assertTrue(status['enabled'])
            self.assertEqual(status['urls'], [f'http://127.0.0.2:{self.port}'])
        async with self.client.get(self.lan) as response:
            self.assertEqual(response.status, 200)
            self.assertFalse((await response.json())['can_configure'])
        async with self.client.put(self.local, json={'enabled': False}) as response:
            self.assertEqual(response.status, 200)
        async with self.client.get(self.local) as response:
            self.assertFalse((await response.json())['enabled'])
        self.assertIs(self.app[APPLICATION], before)
        self.assertEqual(self.runner.addresses, [('127.0.0.1', self.port)])

    async def test_nonlocal_host_and_cross_origin_writes_cannot_toggle_access(self):
        await self.app[NETWORK].change(True)
        for url, headers in ((self.lan, {}), (self.local, {'Origin': 'http://example.invalid'})):
            async with self.client.put(url, json={'enabled': False}, headers=headers) as response:
                self.assertEqual(response.status, 403)
        self.assertTrue(self.app[NETWORK].enabled)

    async def test_a_partial_bind_failure_rolls_back_all_new_listeners(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.3', self.port))
            occupied.listen()
            with patch('backend.listeners.lan_addresses', return_value=['127.0.0.2', '127.0.0.3']):
                async with self.client.put(self.local, json={'enabled': True}) as response:
                    self.assertEqual(response.status, 400)
        self.assertFalse(self.app[NETWORK].enabled)
        self.assertEqual(self.runner.addresses, [('127.0.0.1', self.port)])

    async def test_initial_wildcard_listener_respects_disable_and_mapped_hosts(self):
        await self.runner.cleanup()
        # A fresh application is required after a runner has shut down.
        self.app = web.Application(middlewares=[boundary])
        self.app[NETWORK] = NetworkAccess(True)
        self.app[APPLICATION] = SimpleNamespace(update_installing=False, active_writes=0, events=EventHub())
        self.app.add_routes([web.get('/api/settings/network', network_settings), web.put('/api/settings/network', network_settings)])
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        await self.app[NETWORK].start(self.runner, host='0.0.0.0', port=0)
        address = f'http://127.0.0.1:{self.app[NETWORK].port}/api/settings/network'
        async with self.client.get(address, headers={'Host': '192.168.50.10:8191'}) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())['urls'][0], 'http://192.168.50.10:8191')
        async with self.client.put(address, json={'enabled': False}) as response:
            self.assertEqual(response.status, 200)
        async with self.client.get(address, headers={'Host': '192.168.50.10:8191'}) as response:
            self.assertEqual(response.status, 403)
        async with self.client.get(address) as response:
            self.assertEqual(response.status, 200)


class NativeRunnerTests(unittest.TestCase):
    def test_actual_runner_handles_graceful_exit(self):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        script = f'''
import asyncio
from aiohttp import web
from backend.listeners import NETWORK, NetworkAccess, run_server
app = web.Application()
app[NETWORK] = NetworkAccess()
def stop():
    raise web.GracefulExit()
async def handler(request):
    if request.path == '/stop':
        asyncio.get_running_loop().call_later(.05, stop)
    return web.json_response({{'ready': True}})
app.router.add_get('/ready', handler)
app.router.add_get('/stop', handler)
run_server(app, port={port})
'''
        child = subprocess.Popen([sys.executable, '-c', script], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        opener = build_opener(ProxyHandler({}))
        try:
            for _ in range(100):
                try:
                    with opener.open(f'http://127.0.0.1:{port}/ready', timeout=.2) as response:
                        self.assertEqual(response.status, 200)
                    break
                except OSError:
                    if child.poll() is not None:
                        self.fail(child.communicate()[1].decode(errors='replace'))
                    time.sleep(.05)
            else:
                self.fail('The isolated HTTP runner did not become ready')
            with opener.open(f'http://127.0.0.1:{port}/stop', timeout=2):
                pass
            _, errors = child.communicate(timeout=10)
            self.assertEqual(child.returncode, 0, errors.decode(errors='replace'))
        finally:
            if child.poll() is None:
                child.terminate()
                child.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
