"""Proxy routing against local fixtures only; no cloud or GPU requests."""
import asyncio
import base64
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

from backend.network import open_url, proxy_for_url, tls_context
from backend.generation import create_backend
from backend.generation.comfyui import ComfyBackend
from test_backend import config as comfy_config

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')


class SystemTrustSmoke(unittest.TestCase):
    def test_tls_context_keeps_certificate_and_hostname_verification(self):
        original = ssl.SSLContext
        tls_context.cache_clear()
        context = tls_context()
        self.assertIs(context, tls_context())
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertIs(ssl.SSLContext, original)
        if sys.platform == 'darwin':
            import truststore
            self.assertIsInstance(context, truststore.SSLContext)


@unittest.skipUnless(sys.platform == 'darwin', 'macOS native certificate verification')
class MacTLSRejectionSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_untrusted_server_is_rejected_by_sync_and_async_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            certificate, key = Path(directory) / 'cert.pem', Path(directory) / 'key.pem'
            subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(key), '-out', str(certificate), '-days', '1',
                            '-subj', '/CN=localhost'], check=True, capture_output=True)
            server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_tls.load_cert_chain(certificate, key)
            app = web.Application()
            async def response(request):
                return web.Response(text='untrusted')
            app.router.add_get('/', response)
            server = TestServer(app, scheme='https')
            await server.start_server(ssl=server_tls)
            try:
                def download():
                    with open_url(str(server.make_url('/')), timeout=5) as response:
                        return response.read()
                with self.assertRaises(OSError) as failure:
                    await asyncio.to_thread(download)
                self.assertIsInstance(failure.exception.reason, ssl.SSLCertVerificationError)
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=tls_context())) as client:
                    with self.assertRaises(aiohttp.ClientConnectorCertificateError):
                        await client.get(server.make_url('/'))
            finally:
                await server.close()


class ProxyRulesSmoke(unittest.TestCase):
    def test_system_proxy_is_used_only_for_external_addresses(self):
        with patch('backend.network.getproxies', return_value={'http': 'http://proxy:8080', 'https': 'http://proxy:8081'}), \
                patch('backend.network.proxy_bypass', return_value=False):
            for host in ('localhost', 'LOCALHOST.', 'test.localhost', '127.0.0.1', '127.0.0.2',
                         '10.0.0.7', '172.16.0.3', '192.168.50.49', '[::1]', '[fd00::1]',
                         '[fe80::1]', '[::ffff:192.168.1.2]', 'my-comfy', 'my-comfy.local', 'my-comfy.lan'):
                self.assertIsNone(proxy_for_url(f'http://{host}:8188/prompt'), host)
            self.assertEqual(proxy_for_url('https://huggingface.co/model'), 'http://proxy:8081')
            self.assertEqual(proxy_for_url('wss://events.example.com/ws'), 'http://proxy:8081')
            self.assertEqual(proxy_for_url('ws://events.example.com/ws'), 'http://proxy:8080')
        with patch('backend.network.getproxies', return_value={}), patch('backend.network.proxy_bypass', return_value=False):
            self.assertIsNone(proxy_for_url('https://example.com'))

    def test_environment_and_no_proxy_are_respected(self):
        with patch.dict(os.environ, {'https_proxy': 'http://lower:8000',
                                   'no_proxy': '.internal.example.com,example.org:8443'}, clear=True):
            self.assertEqual(proxy_for_url('https://example.com'), 'http://lower:8000')
            self.assertIsNone(proxy_for_url('https://api.internal.example.com'))
            self.assertIsNone(proxy_for_url('https://example.org:8443'))
            self.assertEqual(proxy_for_url('https://example.org:443'), 'http://lower:8000')
        with patch.dict(os.environ, {'http_proxy': 'http://proxy:8000', 'no_proxy': '*'}, clear=True):
            self.assertIsNone(proxy_for_url('http://example.com'))


class ProxyTransportSmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.direct_headers = []
        origin = web.Application()
        async def direct(request):
            self.direct_headers.append(dict(request.headers))
            return web.Response(body=b'direct download')
        origin.router.add_get('/download', direct)
        self.origin = TestServer(origin)
        await self.origin.start_server()
        proxy = web.Application()
        proxy.router.add_route('*', '/{path:.*}', self.handle_proxy)
        self.proxy = TestServer(proxy)
        await self.proxy.start_server()
        proxy_url = str(self.proxy.make_url('/')).rstrip('/').replace('http://', 'http://proxy-user:proxy-password@')
        self.environment = patch.dict(os.environ, {'http_proxy': proxy_url, 'https_proxy': proxy_url, 'no_proxy': ''}, clear=True)
        self.environment.start()
        self.session = aiohttp.ClientSession(trust_env=False)

    async def asyncTearDown(self):
        await self.session.close()
        self.environment.stop()
        await self.proxy.close()
        await self.origin.close()

    async def handle_proxy(self, request):
        self.calls.append((request.method, request.raw_path, dict(request.headers)))
        if request.path == '/redirect':
            raise web.HTTPFound(str(self.origin.make_url('/download')))
        if request.path == '/download':
            return web.Response(body=b'proxied download')
        if request.path == '/image.png':
            return web.Response(body=PNG, content_type='image/png')
        if request.path == '/ws':
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for _ in ws:
                pass
            return ws
        if request.method == 'POST':
            await request.json()
            if request.path.endswith('/interactions'):
                return web.json_response({'status': 'completed', 'steps': [{'type': 'model_output', 'content': [
                    {'type': 'image', 'data': base64.b64encode(PNG).decode(), 'mime_type': 'image/png'}]}]})
            return web.json_response({'data': [{'url': 'http://images.proxy-test.invalid/image.png'}]})
        return web.json_response({'id': 'fixture-model'})

    async def test_cloud_generation_and_image_download_share_proxy_without_api_credential_leak(self):
        for kind in ('openai', 'gemini'):
            backend = create_backend({'kind': kind, 'id': kind, 'name': kind, 'model': 'fixture-model',
                'base_url': 'http://api.proxy-test.invalid/' + ('v1' if kind == 'openai' else 'v1beta'),
                'api_key': 'fixture-provider-key'}, self.session)
            self.assertTrue((await backend.check())['ok'])
            completed = await backend.submit({'positive': 'garden'}, 'fixture-job')
            self.assertEqual(await backend.image(completed.outputs[0]), (PNG, 'image/png'))
        image = next(call for call in self.calls if call[1].endswith('/image.png'))
        self.assertNotIn('Authorization', image[2])
        self.assertNotIn('x-goog-api-key', image[2])
        self.assertTrue(all(call[2].get('Proxy-Authorization', '').startswith('Basic ') for call in self.calls))
        self.assertTrue(all(call[1].startswith('http://') for call in self.calls))

    async def test_download_redirect_and_local_request_bypass_proxy_and_strip_proxy_credentials(self):
        def download(url):
            with open_url(Request(url), timeout=5) as response:
                return response.read()
        self.assertEqual(await asyncio.to_thread(download, 'http://downloads.proxy-test.invalid/download'), b'proxied download')
        self.assertEqual(await asyncio.to_thread(download, 'http://downloads.proxy-test.invalid/redirect'), b'direct download')
        self.assertEqual(await asyncio.to_thread(download, str(self.origin.make_url('/download'))), b'direct download')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.direct_headers), 2)
        self.assertTrue(all('Proxy-Authorization' not in headers for headers in self.direct_headers))

    async def test_comfy_websocket_uses_same_proxy(self):
        backend = ComfyBackend(comfy_config('http://comfy.proxy-test.invalid'), self.session)
        try:
            self.assertTrue(await backend.start_events('fixture-request', lambda: None))
            self.assertIn('/ws?', self.calls[0][1])
        finally:
            await backend.stop_events()
