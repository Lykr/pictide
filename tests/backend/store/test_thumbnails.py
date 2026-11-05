import asyncio
import hashlib
import os
from pathlib import Path
import stat
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from backend.domain import BackendError
from backend.store.cleanup import delete_pending
from backend.store.thumbnails import ThumbnailCache, thumbnail_path
from tests.backend.store.test_cleanup import CleanupFixture


class ThumbnailTests(CleanupFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cache = ThumbnailCache(self.repo, self.paths)

    async def asyncTearDown(self):
        await self.cache.stop()

    def picture(self, size=(1200, 900), *, old=False):
        identifier, source, _ = self.artifact(self.old() if old else None)
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('parameters', 'private generation metadata')
        with Image.new('RGB', size, 'navy') as image:
            image.save(source, pnginfo=metadata)
        return identifier, source

    async def test_preview_is_smaller_preserves_originals_and_reuses_cache_after_restart(self):
        identifier, source = self.picture()
        original = source.read_bytes(), source.with_suffix('.json').read_bytes()
        self.assertFalse((self.paths.cache / 'thumbnails').exists())
        target = await self.cache.image(identifier, source)
        with Image.open(target) as preview:
            self.assertEqual(preview.format, 'WEBP')
            self.assertEqual(preview.size, (480, 360))
            self.assertNotIn('parameters', preview.info)
            self.assertNotIn('exif', preview.info)
        self.assertEqual(original, (source.read_bytes(), source.with_suffix('.json').read_bytes()))
        self.assertEqual(list(target.parent.iterdir()), [target])
        second = ThumbnailCache(self.repo, self.paths)
        try:
            with patch('backend.store.thumbnails.Image.open', side_effect=AssertionError('cache was decoded again')):
                self.assertEqual(await self.cache.image(identifier, source), target)
                self.assertEqual(await second.image(identifier, source), target)
        finally:
            await second.stop()

    async def test_changed_original_replaces_the_same_cache_file_once(self):
        identifier, source = self.picture()
        target = await self.cache.image(identifier, source)
        old_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        changed = source.stat().st_mtime_ns + 2_000_000_000
        with Image.new('RGB', (900, 1200), 'lime') as image:
            image.save(source)
        os.utime(source, ns=(changed, changed))
        self.assertEqual(await self.cache.image(identifier, source), target)
        self.assertNotEqual(hashlib.sha256(target.read_bytes()).hexdigest(), old_hash)
        with Image.open(target) as preview:
            self.assertEqual(preview.size, (360, 480))
        with patch('backend.store.thumbnails.Image.open', side_effect=AssertionError('stale mtime')):
            self.assertEqual(await self.cache.image(identifier, source), target)
        self.assertEqual(list(target.parent.iterdir()), [target])

    async def test_small_transparent_oriented_and_animated_sources(self):
        identifier, source = self.picture((32, 64))
        with Image.new('RGBA', (32, 64), (0, 0, 255, 128)) as image:
            image.save(source)
        target = await self.cache.image(identifier, source)
        with Image.open(target) as preview:
            self.assertEqual(preview.size, (32, 64))
            self.assertEqual(preview.getpixel((0, 0))[3], 128)
        oriented, jpeg = self.picture((120, 80))
        with Image.new('RGB', (120, 80), 'red') as image:
            exif = Image.Exif()
            exif[274] = 6
            image.save(jpeg, format='JPEG', exif=exif)
        original = jpeg.read_bytes()
        with Image.open(await self.cache.image(oriented, jpeg)) as preview:
            self.assertEqual(preview.size, (80, 120))
            self.assertNotIn(274, preview.getexif())
        self.assertEqual(jpeg.read_bytes(), original)
        animated, gif = self.picture((100, 60))
        with Image.new('RGB', (100, 60), 'green') as first, Image.new('RGB', (100, 60), 'red') as second:
            first.save(gif, format='GIF', save_all=True, append_images=[second], duration=100, loop=0)
        with Image.open(await self.cache.image(animated, gif)) as preview:
            self.assertEqual(preview.size, (100, 60))
            self.assertFalse(getattr(preview, 'is_animated', False))
            self.assertGreater(preview.getpixel((0, 0))[1], 100)

    async def test_duplicate_readers_share_generation_and_conversion_is_bounded(self):
        pictures = [self.picture((300, 200)) for _ in range(5)]
        render = self.cache._render
        counts = dict(calls=0, active=0, peak=0)
        lock = threading.Lock()
        def record(*arguments):
            with lock:
                counts['calls'] += 1
                counts['active'] += 1
                counts['peak'] = max(counts['peak'], counts['active'])
            try:
                time.sleep(.03)
                return render(*arguments)
            finally:
                with lock:
                    counts['active'] -= 1
        with patch.object(self.cache, '_render', record):
            results = await asyncio.gather(*(self.cache.image(*picture) for picture in pictures for _ in range(4)))
        self.assertTrue(all(target.is_file() for target in results))
        self.assertEqual(counts['calls'], 5)
        self.assertEqual(counts['peak'], 2)

    async def test_disconnecting_one_reader_does_not_cancel_another(self):
        identifier, source = self.picture()
        started, release = threading.Event(), threading.Event()
        render = self.cache._render
        def pause(*arguments):
            started.set()
            if not release.wait(5):
                raise RuntimeError('reader did not release conversion')
            return render(*arguments)
        with patch.object(self.cache, '_render', pause):
            first = asyncio.create_task(self.cache.image(identifier, source))
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            second = asyncio.create_task(self.cache.image(identifier, source))
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            release.set()
            self.assertTrue((await second).is_file())

    async def test_deletion_during_encoding_cannot_write_a_late_preview(self):
        identifier, source = self.picture(old=True)
        encoded, release = threading.Event(), threading.Event()
        save = Image.Image.save
        def pause(image, *arguments, **options):
            result = save(image, *arguments, **options)
            encoded.set()
            if not release.wait(5):
                raise RuntimeError('cleanup did not release conversion')
            return result
        with patch.object(Image.Image, 'save', pause):
            pending = asyncio.create_task(self.cache.image(identifier, source))
            self.assertTrue(await asyncio.to_thread(encoded.wait, 5))
            try:
                self.assertEqual(self.repo.expire_artifacts(self.old()), 1)
                delete_pending(self.repo, self.paths, 100)
            finally:
                release.set()
            self.assertIsNone(await pending)
        self.assertFalse(thumbnail_path(self.paths, identifier).exists())
        self.assertEqual(list(self.paths.tmp.glob('thumbnail-*.part')), [])
        self.assertIsNone(self.repo.artifact(identifier))

    async def test_cleanup_removes_only_the_deleted_artifacts_preview_even_for_shared_originals(self):
        identifier, source = self.picture(old=True)
        other, _, _ = self.artifact(path=source.name)
        with Image.new('RGB', (800, 600), 'navy') as image:
            image.save(source)
        deleted, retained = await asyncio.gather(self.cache.image(identifier, source), self.cache.image(other, source))
        self.assertEqual(self.repo.expire_artifacts(self.old()), 1)
        self.assertEqual(delete_pending(self.repo, self.paths, 100), 0)
        self.assertFalse(deleted.exists())
        self.assertTrue(retained.is_file())
        self.assertTrue(source.is_file())

    async def test_locked_preview_retries_through_the_existing_deletion_queue(self):
        identifier, source = self.picture(old=True)
        target = await self.cache.image(identifier, source)
        self.repo.expire_artifacts(self.old())
        unlink = Path.unlink
        def locked(path, *arguments, **options):
            if path == target:
                raise PermissionError('preview is locked')
            return unlink(path, *arguments, **options)
        with patch.object(Path, 'unlink', locked):
            self.assertEqual(delete_pending(self.repo, self.paths, 100), 0)
        self.assertEqual(self.repo.cleanup_counts()['pending'], 1)
        self.assertEqual(delete_pending(self.repo, self.paths, 100), 1)
        self.assertFalse(target.exists())
        self.assertFalse(source.exists())

    async def test_invalid_files_and_cache_reparse_points_do_not_write_previews(self):
        identifier, source, _ = self.artifact()
        with self.assertRaises(BackendError):
            await self.cache.image(identifier, source)
        self.assertEqual(list(self.paths.tmp.glob('thumbnail-*.part')), [])
        identifier, source = self.picture()
        lstat = Path.lstat
        def reparse(path, *arguments, **options):
            if path == self.paths.cache / 'thumbnails':
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return lstat(path, *arguments, **options)
        with patch.object(Path, 'lstat', reparse), self.assertRaises(BackendError):
            await self.cache.image(identifier, source)

    async def test_shutdown_drains_active_encoding_and_cancels_queued_work(self):
        pictures = [self.picture((300, 200)) for _ in range(4)]
        render = self.cache._render
        started, release = threading.Event(), threading.Event()
        def pause(*arguments):
            started.set()
            if not release.wait(5):
                raise RuntimeError('shutdown did not release conversion')
            return render(*arguments)
        with patch.object(self.cache, '_render', pause):
            readers = [asyncio.create_task(self.cache.image(*picture)) for picture in pictures]
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            stopping = asyncio.create_task(self.cache.stop())
            await asyncio.sleep(0)
            release.set()
            await stopping
            await asyncio.gather(*readers, return_exceptions=True)
        self.assertEqual(self.cache._pending, {})
        self.assertEqual(list(self.paths.tmp.glob('thumbnail-*.part')), [])


if __name__ == '__main__':
    unittest.main()
