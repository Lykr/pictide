"""Disposable image previews; original assets and prompt records stay unchanged."""
import asyncio
import hashlib
import os
from pathlib import Path
import tempfile

from PIL import Image, ImageOps

from ..domain import BackendError
from .assets import is_reparse_point
from .contracts import Storage

THUMBNAIL_SIZE = 480


def thumbnail_path(paths, identifier):
    directory = paths.cache / 'thumbnails'
    target = directory / (hashlib.sha256(identifier.encode('utf-8')).hexdigest() + '.webp')
    for item in (paths.cache, directory, target):
        if is_reparse_point(item):
            raise ValueError('unsafe thumbnail path')
    return target


class ThumbnailCache:
    def __init__(self, repository: Storage, paths):
        self.repository, self.paths = repository, paths
        self._slots = asyncio.Semaphore(2)
        self._pending = {}

    async def image(self, identifier, source):
        work = self._pending.get(identifier)
        if work is None:
            work = asyncio.create_task(self._create(identifier, source))
            self._pending[identifier] = work
            work.add_done_callback(lambda done: self._finished(identifier, done))
        return await asyncio.shield(work)

    def _finished(self, identifier, work):
        if self._pending.get(identifier) is work:
            self._pending.pop(identifier)
        if not work.cancelled():
            work.exception()  # A disconnected reader may no longer await it.

    async def stop(self):
        pending = list(self._pending.values())
        for work in pending:
            work.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _create(self, identifier, source):
        async with self._slots:
            work = asyncio.create_task(asyncio.to_thread(self._render, identifier, source))
            try:
                return await asyncio.shield(work)
            except asyncio.CancelledError:
                await work  # Finish file/SQLite work before shutdown releases data.
                raise

    def _render(self, identifier, source):
        temporary = None
        try:
            source = Path(source)
            original = source.stat()
            target = thumbnail_path(self.paths, identifier)
            if target.is_file() and target.stat().st_mtime_ns == original.st_mtime_ns:
                return target
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix='thumbnail-', suffix='.part', dir=self.paths.tmp)
            os.close(descriptor)
            with Image.open(source) as image:
                ImageOps.exif_transpose(image, in_place=True)
                image.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.Resampling.LANCZOS)
                preview = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
                preview.info.clear()
                try:
                    preview.save(temporary, format='WEBP', quality=80, method=4)
                finally:
                    preview.close()
            os.utime(temporary, ns=(original.st_atime_ns, original.st_mtime_ns))
            # Encode outside the write transaction. Commit alongside the same
            # tombstone/cleanup lock, so deletion cannot leave a late preview.
            with self.repository.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT local_path FROM artifacts WHERE id=? AND deleted_at IS NULL', (identifier,)).fetchone()
                if not row or not row['local_path'] or (self.paths.root / row['local_path']).resolve() != source.resolve():
                    return None
                target = thumbnail_path(self.paths, identifier)
                os.replace(temporary, target)
            return target
        except FileNotFoundError:
            return None
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            raise BackendError('缩略图生成失败，请检查图片文件和缓存目录。') from error
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
