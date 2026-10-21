"""Automatic local connections exist before bootstrap and retain user edits."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, LOCAL_GENERATION, create_app
from backend.setup.local_generation_session import ManagedComfy, _WindowsJob, read_state
from backend.paths import DataPaths
from tests.backend.application.test_app import FakeBackend, configuration


class AutomaticLocalConnectionSmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = DataPaths(self.temporary.name).ensure()
        self.fake = FakeBackend()
        self.host = create_app(self.paths.root, lambda config, session: self.fake)
        self.application = self.host[APPLICATION]
        self.managed = ManagedComfy(self.paths, dict(mode='managed', profile_id='nvidia',
                                    recipe_id='anima-turbo-v1-1', install_dir=str(self.paths.runtime / 'comfyui')))
        self.managed.url = 'http://127.0.0.1:19980'

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def test_first_bootstrap_is_ready_and_user_can_submit_without_settings(self):
        self.managed.start = lambda: self.managed.url
        closed = []
        self.managed.close = lambda: closed.append(True)
        self.host[LOCAL_GENERATION] = self.managed
        async with TestClient(TestServer(self.host)) as client:
            response = await client.get('/api/bootstrap')
            boot = await response.json()
            self.assertEqual(len(boot['backends']), 1)
            backend = boot['backends'][0]
            self.assertEqual(boot['roam_settings']['backend_id'], backend['id'])
            self.assertEqual(backend['workflow']['28']['inputs'], dict(width=832, height=1248, batch_size=1))
            self.assertTrue(backend['workflow_id'])
            self.assertFalse(self.fake.submissions, 'Initialization must not generate an image')
            templates = await (await client.get('/api/workflows')).json()
            self.assertEqual(len(templates['workflows']), 1)
            request = dict(backend_id=backend['id'], request_id='first-local-click',
                           positive='a tree in a park', negative='', seed=7)
            response = await client.post('/api/jobs', json=request)
            self.assertEqual(response.status, 202, await response.text())
            self.assertTrue(read_state(self.paths)['configured'])
        self.assertTrue(closed)

    async def test_restart_preserves_workflow_edits_other_backends_and_user_selection(self):
        await self.managed.configure(self.application, None)
        identifier = self.managed.state['backend_id']
        edited = self.application.storage.backend(identifier)
        edited['workflow']['19']['inputs']['steps'] = 12
        await self.application.save_backend(identifier, edited)
        await self.application.save_backend('other', dict(configuration(), id='other'))
        await self.application.roam_settings({'prefetch_count': 0, 'backend_id': 'other'})
        restarted = ManagedComfy(self.paths, read_state(self.paths))
        restarted.url = 'http://127.0.0.1:19981'
        await restarted.configure(self.application, None)
        stored = self.application.storage.backend(identifier)
        self.assertEqual(stored['workflow']['19']['inputs']['steps'], 12)
        self.assertEqual(stored['base_url'], restarted.url)
        self.assertEqual(self.application.roam.get()['backend_id'], 'other')
        self.assertEqual(len(self.application.storage.backends()), 2)
        await self.application.delete_backend(identifier, {})
        await restarted.configure(self.application, None)
        self.assertIsNone(self.application.storage.backend(identifier))


@unittest.skipUnless(sys.platform == 'win32', 'Win32 process ownership')
class ManagedProcessSmoke(unittest.TestCase):
    def test_job_close_stops_only_its_owned_child(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        job = None
        try:
            job = _WindowsJob(child)
            self.assertIsNone(child.poll())
            job.close()
            self.assertIsNotNone(child.wait(timeout=5))
        finally:
            if job is not None:
                job.close()
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
