from io import BytesIO
import asyncio
import tempfile
import unittest
import zipfile

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from tests.backend.application.test_app import FakeBackend, configuration


class LikedExportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app(self.temporary.name, lambda config, session: FakeBackend())
        application = self.app[APPLICATION]
        application.storage.save_backend({**configuration(), 'id': 'fixture'})
        self.images = []
        for index in range(3):
            job = application.storage.create_job({'request_id': f'export-{index}', 'backend_id': 'fixture',
                                                  'positive': 'garden', 'negative': '', 'seed': index})
            path = application.paths.images / f'{index}.png'
            path.write_bytes(b'original-image-' + bytes([index]))
            application.storage.complete(job['id'], [{'node_id': '9', 'index': 0,
                'local_path': path.relative_to(application.paths.root).as_posix(), 'content_type': 'image/png'}])
            identifier = next(item['id'] for item in application.storage.artifacts() if item['job_id'] == job['id'])
            self.images.append((identifier, path))
        for identifier, _ in self.images[:2]:
            application.storage.rate(identifier, 1)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temporary.cleanup()

    async def test_selected_original_bytes_and_temporary_archive_cleanup(self):
        identifiers = [identifier for identifier, _ in self.images[:2]]
        response = await self.client.post('/api/liked/export', json={'ids': identifiers})
        self.assertEqual(response.status, 200)
        self.assertIn('attachment', response.headers['Content-Disposition'])
        with zipfile.ZipFile(BytesIO(await response.read())) as archive:
            self.assertEqual(set(archive.namelist()), {identifier + '.png' for identifier in identifiers})
            for identifier, path in self.images[:2]:
                self.assertEqual(archive.read(identifier + '.png'), path.read_bytes())
        self.assertEqual(list(self.app[APPLICATION].paths.tmp.glob('liked-*.zip')), [])
        self.assertEqual(self.app[APPLICATION].storage.counts()['liked'], 2)

    async def test_unliked_invalid_and_empty_selections_are_rejected(self):
        for payload in ({'ids': []}, {'ids': ['../image']}, {'ids': [self.images[2][0]]}, {'ids': [self.images[0][0]], 'path': 'outside'}):
            with self.subTest(payload=payload):
                response = await self.client.post('/api/liked/export', json=payload)
                self.assertEqual(response.status, 400)
        self.assertEqual(list(self.app[APPLICATION].paths.tmp.glob('liked-*.zip')), [])

    async def test_interrupted_download_reclaims_the_temporary_archive(self):
        identifier, path = self.images[0]
        path.write_bytes(b'x' * (8 * 1024 * 1024))
        response = await self.client.post('/api/liked/export', json={'ids': [identifier]})
        self.assertEqual(response.status, 200)
        await response.content.read(1024)
        response.close()
        for _ in range(100):
            if not list(self.app[APPLICATION].paths.tmp.glob('liked-*.zip')):
                break
            await asyncio.sleep(.01)
        self.assertEqual(list(self.app[APPLICATION].paths.tmp.glob('liked-*.zip')), [])

    async def test_single_download_requires_a_current_like(self):
        for index, expected in ((0, 200), (2, 400)):
            identifier, path = self.images[index]
            response = await self.client.get(f'/api/artifacts/{identifier}/image?download=1')
            self.assertEqual(response.status, expected)
            if expected == 200:
                self.assertEqual(await response.read(), path.read_bytes())

    async def test_recommended_template_uses_canonical_workflow_and_bindings(self):
        response = await self.client.post('/api/backends/new/template', json={
            'kind': 'comfyui', 'base_url': 'http://127.0.0.1:8188', 'recipe': 'anima-turbo-v1-1'})
        self.assertEqual(response.status, 200)
        template = await response.json()
        self.assertEqual(template['bindings']['positive'], {'node_id': '11', 'input': 'text'})
        self.assertEqual(template['bindings']['width'], {'node_id': '28', 'input': 'width'})
        self.assertEqual(template['output_nodes'], ['1'])
        self.assertEqual(template['workflow']['28']['inputs']['height'], 1248)


if __name__ == '__main__':
    unittest.main()
