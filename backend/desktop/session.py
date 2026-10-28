"""Small desktop lifecycle adapter; the browser remains the application UI."""
import asyncio
import json
import logging
import os
import socket
from pathlib import Path
import sys
import webbrowser
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from .text import translate
from .terminal import Console, status

log = logging.getLogger('backend')


def announce(key, **values):
    message = translate(key, **values)
    status(message)
    log.info(message)


class DesktopSession:
    """Own one desktop service for a data directory, including its tray icon."""
    def __init__(self, paths, url):
        self.paths, self.url = paths, url
        self._lock = None
        self._tray = None
        self.socket = None
        self.info = paths.tmp / 'desktop-instance.json'

    def claim(self):
        import msvcrt
        stream = (self.paths.tmp / 'desktop.lock').open('a+b')
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            stream.close()
            # The existing owner keeps sole ownership of the rotating file.
            from ..runtime_logging import close_application_log
            close_application_log()
            self._open_existing()
            return False
        self._lock = stream
        self._write_info(False)
        return True

    def reserve(self, host, port):
        # Reserve the actual port before preparing resources, without listening.
        # Readiness can then only come from this desktop session's HTTP server.
        from .launcher import reserve_desktop_socket
        self.socket = reserve_desktop_socket(host, port)

    def _write_info(self, ready):
        partial = self.info.with_suffix('.json.part')
        partial.write_text(json.dumps(dict(pid=os.getpid(), url=self.url, ready=ready,
                                          data_directory=str(self.paths.root))), encoding='utf-8')
        partial.replace(self.info)

    def _open_existing(self):
        try:
            info = json.loads(self.info.read_text(encoding='utf-8'))
            url = info['url']
            parsed = urlsplit(url)
            if (not info['ready'] or Path(info['data_directory']).resolve() != self.paths.root
                    or parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}):
                raise ValueError('Desktop instance is not ready')
            with build_opener(ProxyHandler({})).open(url + '/api/bootstrap', timeout=2) as response:
                bootstrap = json.load(response)
            if Path(bootstrap['data_directory']).resolve() != self.paths.root:
                raise ValueError('Another data directory owns this address')
        except (OSError, ValueError, KeyError, TypeError):
            announce('instance_starting')
            return
        announce('already_running')
        webbrowser.open(url)

    def _icon(self):
        if getattr(sys, 'frozen', False):
            return Path(__file__).resolve().parents[1] / 'desktop.ico'
        from PIL import Image
        target = self.paths.cache / 'desktop' / 'pictide.ico'
        target.parent.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).resolve().parents[2] / 'web/public/icons/pictide-512.png'
        with Image.open(source) as image:
            image.convert('RGBA').save(target, format='ICO',
                                       sizes=[(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
        return target

    async def ready(self):
        """Called only after our HTTP listener answers bootstrap successfully."""
        from aiohttp import web
        from .windows_tray import WindowsTray, hide_owned_console
        from .launcher import notify_launcher
        loop = asyncio.get_running_loop()

        def background(action):
            loop.call_soon_threadsafe(lambda: loop.create_task(asyncio.to_thread(action)))

        def stop():
            announce('stopping')
            raise web.GracefulExit()

        self._write_info(True)
        messages = [translate('local_address', address=self.url),
                    translate('data_directory', directory=self.paths.root),
                    translate('startup_log', path=self.paths.logs / 'pictide.log')]
        if self.socket.getsockname()[0] == '0.0.0.0':
            try:
                addresses = sorted(set(socket.gethostbyname_ex(socket.gethostname())[2]))
                for address in addresses:
                    if not address.startswith('127.') and address != '0.0.0.0':
                        messages.append(translate('lan_address', address=f'http://{address}:{self.socket.getsockname()[1]}'))
            except OSError:
                log.exception('Cannot discover LAN addresses')
        for message in (translate('ready'), *messages):
            log.info(message)
        Console().show(translate('ready'), messages)
        try:
            self._tray = WindowsTray(self._icon(), 'Pictide — ' + translate('ready'),
                                     {name: translate(name) for name in ('open', 'logs', 'exit')},
                                     lambda: background(lambda: webbrowser.open(self.url)),
                                     lambda: background(lambda: os.startfile(self.paths.logs / 'pictide.log')),
                                     lambda: loop.call_soon_threadsafe(stop))
            available = await asyncio.to_thread(self._tray.start)
        except (OSError, ValueError, RuntimeError):
            log.exception('Cannot start the desktop tray')
            available = False
        if available:
            notify_launcher('ready')
            hide_owned_console()
        else:
            announce('tray_unavailable')
            if notify_launcher('console'):
                # Let the progress process restart this service in its visible terminal.
                loop.call_soon(stop)
                return False

    def close(self):
        if self._tray is not None:
            self._tray.stop()
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        if self._lock is not None:
            import msvcrt
            self.info.unlink(missing_ok=True)
            self._lock.seek(0)
            msvcrt.locking(self._lock.fileno(), msvcrt.LK_UNLCK, 1)
            self._lock.close()
            self._lock = None
