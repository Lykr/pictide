from io import BytesIO
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image, PngImagePlugin

from backend.host import APPLICATION, create_app
from tests.backend.application.test_app import FakeBackend, configuration


class ThumbnailHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app(self.temporary.name, lambda config, session: FakeBackend())
        application = self.app[APPLICATION]
        application.storage.save_backend({**configuration(), 'id': 'fixture'})
        job = application.storage.create_job({'request_id': 'thumbnail', 'backend_id': 'fixture',
                                              'positive': 'garden', 'negative': '', 'seed': 1})
        self.source = application.paths.images / 'original.png'
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('parameters', 'original metadata')
        with Image.effect_noise((1200, 900), 64).convert('RGB') as image:
            image.save(self.source, pnginfo=metadata)
        application.storage.complete(job['id'], [{'node_id': '9', 'index': 0,
            'local_path': self.source.relative_to(application.paths.root).as_posix(), 'content_type': 'image/png'}])
        self.identifier = application.storage.artifacts()[0]['id']
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temporary.cleanup()

    async def test_thumbnail_is_webp_and_conditional_reads_reuse_it_without_changing_originals(self):
        image_url = f'/api/artifacts/{self.identifier}/image'
        original = self.source.read_bytes()
        response = await self.client.get(image_url + '?thumbnail=1')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, 'image/webp')
        self.assertEqual(response.headers['Cache-Control'], 'private, no-cache')
        preview_bytes = await response.read()
        self.assertLess(len(preview_bytes), len(original) // 5)
        with Image.open(BytesIO(preview_bytes)) as preview:
            self.assertEqual(preview.size, (480, 360))
        cached = await self.client.get(image_url + '?thumbnail=1', headers={'If-None-Match': response.headers['ETag']})
        self.assertEqual(cached.status, 304)
        response = await self.client.get(image_url)
        self.assertEqual(response.content_type, 'image/png')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(await response.read(), original)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(len(list(self.app[APPLICATION].paths.cache.rglob('*.webp'))), 1)

    async def test_download_always_returns_original_and_requires_a_like(self):
        url = f'/api/artifacts/{self.identifier}/image?thumbnail=1&download=1'
        self.assertEqual((await self.client.get(url)).status, 400)
        self.app[APPLICATION].storage.rate(self.identifier, 1)
        response = await self.client.get(url)
        self.assertEqual(response.status, 200)
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertEqual(response.content_type, 'image/png')
        self.assertEqual(await response.read(), self.source.read_bytes())

    async def test_cached_thumbnail_is_not_served_after_its_artifact_is_deleted(self):
        url = f'/api/artifacts/{self.identifier}/image?thumbnail=1'
        self.assertEqual((await self.client.get(url)).status, 200)
        self.app[APPLICATION].storage.clear_generated(self.identifier)
        self.assertEqual((await self.client.get(url)).status, 404)
        self.assertEqual((await self.client.get('/api/artifacts/missing/image?thumbnail=1')).status, 404)

    async def test_legacy_uncached_image_is_fetched_through_the_existing_original_path(self):
        application = self.app[APPLICATION]
        job = application.storage.create_job({'request_id': 'legacy', 'backend_id': 'fixture',
                                              'positive': 'garden', 'negative': '', 'seed': 2})
        application.storage.complete(job['id'], [{'node_id': '9', 'index': 0}])
        artifact = next(item for item in application.storage.artifacts() if item['job_id'] == job['id'])
        response = await self.client.get(f'/api/artifacts/{artifact["id"]}/image?thumbnail=1')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, 'image/webp')
        stored = application.storage.artifact(artifact['id'])
        self.assertIsNotNone(stored['local_path'])
        self.assertEqual(stored['feedback'], None)
        self.assertTrue((application.paths.root / stored['local_path']).is_file())


if __name__ == '__main__':
    unittest.main()
