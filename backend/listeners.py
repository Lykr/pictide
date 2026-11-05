"""Host-owned listeners and access state for this running application."""
import asyncio
import ipaddress
import logging
import socket
import weakref

from aiohttp import web

from .domain import ValidationError


def lan_addresses():
    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        addresses = []
    primary = None
    try:
        # UDP connect selects a local route without sending a packet.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(('192.0.2.1', 9))
            primary = probe.getsockname()[0]
    except OSError:
        pass
    if primary:
        addresses.append(primary)
    return sorted({address for address in addresses
                   if ipaddress.ip_address(address).is_private
                   and not ipaddress.ip_address(address).is_loopback
                   and not ipaddress.ip_address(address).is_unspecified}, key=lambda address: (address != primary, address))


class NetworkAccess:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.port = None
        self.runner = None
        self.wildcard = False
        self.sites = []
        self.transports = weakref.WeakSet()
        self.lock = asyncio.Lock()

    async def start(self, runner, *, host='127.0.0.1', port=8189, sock=None):
        self.runner = runner
        self.wildcard = (sock.getsockname()[0] if sock else host) in ('0.0.0.0', '::')
        site = web.SockSite(runner, sock) if sock else web.TCPSite(runner, host, port)
        await site.start()
        self.port = runner.addresses[0][1]

    def track(self, request):
        if request.transport and not ipaddress.ip_address(request.remote or '127.0.0.1').is_loopback:
            self.transports.add(request.transport)

    async def status(self):
        try:
            addresses = await asyncio.to_thread(lan_addresses) if self.enabled else []
        except OSError:
            addresses = []
        return {'enabled': self.enabled, 'available': self.runner is not None,
                'urls': [f'http://{address}:{self.port}' for address in addresses] if self.port else []}

    async def change(self, enabled):
        if self.runner is None:
            raise ValidationError('This instance cannot change its network listeners.')
        async with self.lock:
            if enabled == self.enabled:
                return await self.status()
            if enabled and not self.wildcard:
                addresses = await asyncio.to_thread(lan_addresses)
                if not addresses:
                    raise ValidationError('No LAN address is available. Connect this computer to a local network first.')
                started = []
                try:
                    for address in addresses:
                        site = web.TCPSite(self.runner, address, self.port)
                        await site.start()
                        started.append(site)
                except BaseException:
                    for site in started:
                        await site.stop()
                    raise
                self.sites = started
            self.enabled = enabled
            if not enabled:
                for transport in tuple(self.transports):
                    transport.close()
                self.transports.clear()
                for site in self.sites:
                    await site.stop()
                self.sites.clear()
            logging.getLogger('backend').info('LAN access enabled=%s port=%s', enabled, self.port)
            return await self.status()


def run_server(app, *, host='127.0.0.1', port=8189, sock=None):
    async def serve():
        runner = web.AppRunner(app, access_log=None, handle_signals=True)
        try:
            await runner.setup()
            await app[NETWORK].start(runner, host=host, port=port, sock=sock)
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    try:
        asyncio.run(serve())
    except (KeyboardInterrupt, web.GracefulExit):
        pass


NETWORK = web.AppKey('network_access', NetworkAccess)
