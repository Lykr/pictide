"""Explicit update operations. Status reads and construction never contact the network."""
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import platform
import shutil
import threading
import time
from urllib.request import Request

from .. import __version__
from ..network import open_url
from .installation import detect_installation, extract_package, install_reason
from .lock import UpdateLease
from .releases import PAGE, read_release

log = logging.getLogger('backend')


class UpdateService:
    def __init__(self, paths, *, installation=None, discover=read_release, opener=open_url, on_change=None):
        self.paths = paths
        self.installation = installation if installation is not None else detect_installation()
        self.discover, self.opener = discover, opener
        self.on_change = on_change or (lambda: None)
        self.release = None
        self.package = None
        self.task = None
        self.lease = None
        self.cancelled = threading.Event()
        self.lock = asyncio.Lock()
        self.loop = None
        self.state = dict(current_version=__version__, latest_version=None, phase='idle',
                          compatible=False, reason=install_reason(self.installation, paths.root),
                          release_url=PAGE, downloaded_bytes=0, total_bytes=0, error=None)
        result = paths.tmp / 'updates/result.json'
        if result.is_file():
            try:
                previous = json.loads(result.read_text(encoding='utf8'))
                if previous.get('phase') == 'rolled_back':
                    self.state.update(phase='rolled_back', error='Update failed and the previous version was restored: ' + str(previous.get('error', '')))
            except (OSError, ValueError):
                log.warning('Cannot read the previous update result')

    def status(self):
        reason = install_reason(self.installation, self.paths.root)
        return {**self.state, 'installation': self.installation.root if self.installation else None, 'data_directory': str(self.paths.root),
                'can_download': bool(self.release and self.release.compatible and not reason),
                'can_install': bool(self.package and self.state['phase'] == 'ready' and not reason)}

    def publish(self, **values):
        self.state.update(values)
        if self.loop:
            self.loop.call_soon_threadsafe(self.on_change)

    async def check(self):
        if self.lock.locked() or self.task and not self.task.done():
            return self.status()
        async with self.lock:
            self.loop = asyncio.get_running_loop()
            self.publish(phase='checking', error=None)
            try:
                system = self.installation.platform if self.installation else __import__('sys').platform
                arch = self.installation.arch if self.installation else platform.machine().lower()
                release = await asyncio.to_thread(self.discover, __version__, system, arch)
                if self.release != release:
                    self.package = None
                self.release = release
                reason = install_reason(self.installation, self.paths.root) or release.reason
                self.publish(latest_version=release.version, release_url=release.page, compatible=release.compatible,
                             reason=reason, phase='current' if release.reason == 'already_current' else 'ready' if self.package else 'checked')
                log.info('Update checked current=%s latest=%s compatible=%s', __version__, release.version, release.compatible)
            except Exception as error:
                self.publish(phase='error', error=str(error))
                log.warning('Update check failed: %s', error)
            return self.status()

    def start_download(self):
        from .apply import active_install
        if self.task and not self.task.done():
            return self.status()
        if self.lock.locked() or not self.status()['can_download']:
            raise ValueError('This release cannot be installed directly. Open the release page for manual update instructions.')
        if active_install(self.paths.root):
            raise ValueError('An update installation is already running')
        self.lease = UpdateLease(self.paths.root)
        self.loop = asyncio.get_running_loop()
        self.cancelled.clear()
        self.publish(phase='downloading', downloaded_bytes=0, total_bytes=self.release.asset['bytes'], error=None)
        self.task = asyncio.create_task(self._download(), name='pictide-update-download')
        return self.status()

    async def _download(self):
        async with self.lock:
            try:
                self.package = await asyncio.to_thread(self._download_package)
                self.publish(phase='ready')
            except Exception as error:
                self.publish(phase='error', error=str(error))
                log.warning('Update download failed: %s', error)
            finally:
                self.lease.close()
                self.lease = None

    def _download_package(self):
        release = self.release
        directory = self.paths.cache / 'updates' / release.version
        directory.mkdir(parents=True, exist_ok=True)
        required = release.asset['bytes'] + release.asset['unpacked_bytes'] * 3
        if shutil.disk_usage(directory).free < required:
            raise ValueError('Not enough free space to download and prepare this update')
        archive = directory / release.asset['name']
        def checksum(path):
            with path.open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').hexdigest()
        if not archive.exists() or archive.stat().st_size != release.asset['bytes'] or checksum(archive) != release.asset['sha256']:
            partial = archive.with_suffix('.zip.part')
            try:
                read = 0
                last = 0
                request = Request(release.asset['url'], headers={'User-Agent': 'Pictide-updates'})
                with self.opener(request, timeout=30) as response, partial.open('wb') as output:
                    while chunk := response.read(1024 * 1024):
                        if self.cancelled.is_set():
                            raise RuntimeError('Update download cancelled')
                        read += len(chunk)
                        if read > release.asset['bytes']:
                            raise ValueError('Update download exceeds its declared size')
                        output.write(chunk)
                        if time.monotonic() - last > .15:
                            self.publish(downloaded_bytes=read)
                            last = time.monotonic()
                if read != release.asset['bytes'] or checksum(partial) != release.asset['sha256']:
                    raise ValueError('Update download checksum or size does not match')
                partial.replace(archive)
            finally:
                partial.unlink(missing_ok=True)
        self.publish(phase='verifying', downloaded_bytes=release.asset['bytes'])
        return extract_package(archive, directory / 'unpacked', release, self.installation)

    async def close(self):
        self.cancelled.set()
        if self.task:
            await self.task
