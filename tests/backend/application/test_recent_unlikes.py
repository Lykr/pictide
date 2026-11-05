import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from tests.backend.application.test_app import FakeBackend, configuration


class RecentUnlikeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app(self.temporary.name, lambda config, session: FakeBackend())
        application = self.app[APPLICATION]
        application.storage.save_backend({**configuration(), 'id': 'fixture'})
        job = application.storage.create_job({'request_id': 'recovery', 'backend_id': 'fixture',
                                              'positive': 'garden', 'negative': '', 'seed': 1})
        path = application.paths.images / 'recovery.png'
        path.write_bytes(b'original-image')
        application.storage.complete(job['id'], [{'node_id': '9', 'index': 0,
            'local_path': path.relative_to(application.paths.root).as_posix(), 'content_type': 'image/png'}])
        self.identifier = application.storage.artifacts()[0]['id']
        application.storage.rate(self.identifier, 1)
        application.storage.clear_generated(self.identifier)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temporary.cleanup()

    async def test_hidden_image_can_be_recovered_without_a_new_write_endpoint(self):
        feedback = f'/api/artifacts/{self.identifier}/feedback'
        response = await self.client.put(feedback, json={'value': None})
        self.assertEqual(response.status, 200)
        response = await self.client.get('/api/liked/recently-unliked?limit=1')
        self.assertEqual(response.status, 200)
        window = await response.json()
        self.assertEqual(window['total'], 1)
        self.assertEqual(window['artifacts'][0]['id'], self.identifier)
        self.assertGreater(window['artifacts'][0]['unliked_protected_until'], window['server_time'])
        image = f'/api/artifacts/{self.identifier}/image'
        self.assertEqual((await self.client.get(image + '?download=1')).status, 400)
        self.assertEqual(await (await self.client.get(image)).read(), b'original-image')
        for _ in range(2):  # A repeated restore is an idempotent like.
            response = await self.client.put(feedback, json={'value': 1})
            self.assertEqual(response.status, 200)
        window = await (await self.client.get('/api/liked/recently-unliked')).json()
        self.assertEqual(window['artifacts'], [])
        self.assertEqual(self.app[APPLICATION].storage.counts()['liked'], 1)
        self.assertEqual((await self.client.get(image + '?download=1')).status, 200)
        generated = await (await self.client.get('/api/artifacts?source=generate')).json()
        self.assertEqual(generated['artifacts'], [])

    async def test_bad_paging_is_reported_as_a_client_error(self):
        for query in ('limit=0', 'limit=201', 'limit=1.5', 'before=invalid', 'before='):
            with self.subTest(query=query):
                response = await self.client.get('/api/liked/recently-unliked?' + query)
                self.assertEqual(response.status, 400)


if __name__ == '__main__':
    unittest.main()
