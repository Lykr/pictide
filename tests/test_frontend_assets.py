"""Single frontend entry and deep links must load their compiled graph under the strict local CSP."""
import re
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer
from backend.host import create_app


class FrontendAssetsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.client = TestClient(TestServer(create_app(self.directory.name)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def check_page(self, path):
        page = await self.client.get(path)
        self.assertEqual(page.status, 200)
        self.assertIn("script-src 'self'", page.headers['Content-Security-Policy'])
        html = await page.text()
        assets = re.findall(r'(?:src|href)="(/static/ui/[^" ]+)"', html)
        self.assertGreaterEqual(len(assets), 2)
        visited = set()
        while assets:
            path = assets.pop()
            if path in visited:
                continue
            visited.add(path)
            response = await self.client.get(path)
            self.assertEqual(response.status, 200, path)
            body = await response.text()
            self.assertTrue(body.strip(), path)
            if path.endswith('.js'):
                self.assertIn('javascript', response.headers['Content-Type'])
                for relative in re.findall(r'["\'](\.?\.?/[^"\']+\.js)["\']', body):
                    from urllib.parse import urljoin
                    assets.append(urljoin(path, relative))
                assets.extend(re.findall(r'["\'](/static/ui/[^"\']+\.js)["\']', body))
            elif path.endswith('.css'):
                self.assertIn('text/css', response.headers['Content-Type'])
        self.assertGreater(len(visited), 3)

    async def test_feed_compiled_assets_resolve(self):
        await self.check_page('/')

    async def test_editor_link_redirects_to_single_entry(self):
        response = await self.client.get("/prompts?config=library.json", allow_redirects=False)
        self.assertEqual(response.status, 302)
        self.assertEqual(response.headers["Location"], "/?config=library.json#prompts")
        await self.check_page("/")
