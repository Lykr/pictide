"""LAN host boundary smoke tests; no application data or GPU tasks."""
import unittest
from unittest.mock import Mock

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from backend.host import ALLOW_LAN, boundary


class LanAccessTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, host, *, lan=False, method="GET", origin=None):
        app = web.Application()
        app[ALLOW_LAN] = lan
        transport = Mock()
        transport.get_extra_info.return_value = ("192.168.50.50", 8189)
        headers = {"Host": host, "Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = make_mocked_request(method, "/api/settings/general", headers=headers,
                                      app=app, transport=transport)
        async def handler(request):
            return web.json_response({"ok": True})
        return await boundary(request, handler)

    async def test_local_default_and_explicit_lan(self):
        self.assertEqual((await self.request("127.0.0.1:8189")).status, 200)
        self.assertEqual((await self.request("192.168.50.50:8189")).status, 403)
        self.assertEqual((await self.request("192.168.50.50:8189", lan=True)).status, 200)
        self.assertEqual((await self.request("foreign.example:8189", lan=True)).status, 403)
        self.assertEqual((await self.request("192.168.50.99:8189", lan=True)).status, 403)

    async def test_lan_modifications_keep_origin_protection(self):
        same = await self.request("192.168.50.50:8189", lan=True, method="PUT",
                                  origin="http://192.168.50.50:8189")
        cross = await self.request("192.168.50.50:8189", lan=True, method="PUT",
                                   origin="http://foreign.example")
        self.assertEqual(same.status, 200)
        self.assertEqual(cross.status, 403)
