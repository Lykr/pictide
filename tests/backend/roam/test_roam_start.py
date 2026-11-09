"""A liked original can become the Roam cursor without changing its source."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, create_app
from backend.store.roam_settings import RoamSettings
from backend.store.sqlite import Repository
from tests.backend.application.test_app import FakeBackend, configuration


class RoamStartTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        static = root / 'static'
        static.mkdir()
        self.static = patch('backend.host.STATIC', static)
        self.static.start()
        self.backend = FakeBackend()
        self.app = create_app(root / 'data', lambda config, session: self.backend)
        self.application = self.app[APPLICATION]
        self.repo = self.application.storage
        self.repo.save_backend({**configuration(), 'id': 'fixture'})
        self.application.roam.save(0, 'fixture', '', 20, prompt_mode='stay', playback_style='scroll')
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        await self.application.tasks.stop()
        self.number = 0

    async def asyncTearDown(self):
        await self.client.close()
        self.static.stop()
        self.directory.cleanup()

    def image(self, *, roam=False, hidden=False, liked=True, snapshot=None):
        self.number += 1
        job = self.repo.create_job({'request_id': f'start-{self.number}', 'backend_id': 'fixture',
                                    'positive': 'garden, sky', 'negative': 'blurry', 'seed': self.number,
                                    **({'prompt_snapshot': snapshot} if snapshot else {})})
        if roam:
            candidate = {'candidate_id': 'original', 'positive': 'garden, sky', 'negative': 'blurry',
                         'terms': [], 'rendered': {'positive': 'A garden.', 'negative': '', 'signature': 'saved'}}
            with self.repo.connection() as db:
                db.execute('INSERT INTO roam_jobs VALUES (?,?,?,?,?)',
                           (job['id'], self.application.roam.get()['epoch'], json.dumps(candidate), job['created_at'],
                            'old' if hidden else None))
        path = self.application.paths.images / f'{self.number}.png'
        path.write_bytes(b'unchanged-original')
        self.repo.complete(job['id'], [{'node_id': '9', 'index': 0, 'local_path': path.relative_to(self.application.paths.root).as_posix(),
                                      'content_type': 'image/png'}])
        item = next(item for item in self.repo.artifacts() if item['job_id'] == job['id'])
        if liked:
            self.repo.rate(item['id'], 1)
        if hidden:
            with self.repo.connection() as db:
                db.execute('UPDATE artifacts SET roam_hidden_at=?,generated_hidden_at=? WHERE id=?', ('old', 'old', item['id']))
        return item, path

    async def start(self, identifier):
        response = await self.client.post('/api/roam/start', json={'artifact_id': identifier})
        self.assertEqual(response.status, 200, await response.text())
        return await response.json()

    async def test_manual_original_is_referenced_and_survives_reopening_the_database(self):
        selected, path = self.image()
        self.application.roam.save_options(anchors={'pinned_positive': ['old subject'],
            'excluded_positive': ['old exclusion'], 'pinned_canvas': {'width': 768, 'height': 1024},
            'preset_base_positive': ['preset style']})
        before = self.application.roam.get()
        with self.repo.connection() as db:
            feedback = [tuple(row) for row in db.execute('SELECT * FROM feedback')]
            counts = tuple(db.execute('SELECT (SELECT count(*) FROM jobs),(SELECT count(*) FROM artifacts)').fetchone())
        view = await self.start(selected['id'])
        self.assertEqual(view['artifact_id'], selected['id'])
        self.assertEqual(self.repo.roam_view(), view)
        after = self.application.roam.get()
        self.assertNotEqual(before.pop('epoch'), after.pop('epoch'))
        for key, value in {'pinned_positive': [], 'excluded_positive': [], 'pinned_canvas': None}.items():
            self.assertEqual(after[key], value)
            before[key] = value
        self.assertEqual(before, after)
        self.assertEqual(self.repo.artifacts(source='roam')[0]['source'], 'generate')
        self.assertEqual(self.repo.artifacts(source='generate')[0]['id'], selected['id'])
        self.assertEqual(path.read_bytes(), b'unchanged-original')
        self.assertEqual(list(self.application.paths.images.iterdir()), [path])
        with self.repo.connection() as db:
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM feedback')], feedback)
            self.assertEqual(tuple(db.execute('SELECT (SELECT count(*) FROM jobs),(SELECT count(*) FROM artifacts)').fetchone()), counts)
        reopened = Repository(self.application.paths.database)
        self.assertEqual(reopened.roam_view(), view)
        self.assertEqual(reopened.artifact_page(source='roam', around=selected['id'])['anchor_id'], selected['id'])
        self.assertEqual(RoamSettings(self.application.paths).get(), self.application.roam.get())
        self.assertEqual(self.backend.submissions, [])

    async def test_hidden_roam_image_replaces_old_future_and_inflight_results(self):
        selected, path = self.image(roam=True, hidden=True)
        future, future_path = self.image(roam=True)
        old = self.application.roam.get()['epoch']
        queued = self.repo.ensure_roam(old, None, 20, {'request_id': 'queued', 'backend_id': 'fixture',
            'positive': 'garden', 'negative': '', 'seed': 1}, {'positive': 'garden', 'negative': ''})['job']
        running = self.repo.ensure_roam(old, None, 20, {'request_id': 'running', 'backend_id': 'fixture',
            'positive': 'sky', 'negative': '', 'seed': 1}, {'positive': 'sky', 'negative': ''})['job']
        self.repo.claim_job(running['id'])
        self.repo.attach_prompt(running['id'], 'accepted-old-job')
        self.repo.update_job(running['id'], 'running')
        revision = self.repo.artifact_revision()
        view = await self.start(selected['id'])
        self.assertGreater(self.repo.artifact_revision(), revision)
        self.assertEqual([a['id'] for a in self.repo.artifacts(source='roam')], [selected['id']])
        self.assertEqual(self.repo.job(queued['id'])['status'], 'cancelled')
        self.assertEqual(self.repo.artifact(future['id'])['feedback'], 1)
        self.assertTrue(future_path.exists())
        self.assertTrue(path.exists())
        reference = self.repo.roam_prompt_reference(self.application.roam.get()['epoch'], selected['id'])
        self.assertEqual(reference['rendered']['positive'], 'A garden.')
        self.repo.complete(running['id'], [{'node_id': '9', 'index': 0}])
        self.assertEqual([a['id'] for a in self.repo.artifacts(source='roam')], [selected['id']])
        self.repo.roam_view({'artifact_id': None, 'viewed_at': view['viewed_at'] - 1})
        self.assertEqual(self.repo.roam_view(), view)

    async def test_repeated_unhide_keeps_revisions_increasing_and_old_origins_in_history(self):
        first, _ = self.image(hidden=True)
        second, _ = self.image(roam=True, hidden=True)
        revision = self.repo.artifact_revision()
        for item in (first, second, first, second):
            await self.start(item['id'])
            self.assertGreater(self.repo.artifact_revision(), revision)
            revision = self.repo.artifact_revision()
            self.assertEqual(self.repo.roam_view()['artifact_id'], item['id'])
        self.assertEqual({a['id'] for a in self.repo.artifacts(source='roam')}, {first['id'], second['id']})

    async def test_hidden_generate_image_keeps_hidden_generate_state_and_source_prompts(self):
        selected, _ = self.image(hidden=True, snapshot={'positive': 'garden, sky', 'negative': 'blurry'})
        await self.start(selected['id'])
        self.assertEqual(self.repo.artifacts(source='generate'), [])
        self.assertEqual(self.repo.artifacts(liked=True)[0]['id'], selected['id'])
        reference = self.repo.roam_prompt_reference(self.application.roam.get()['epoch'], selected['id'])
        self.assertEqual(reference['positive'], 'garden, sky')
        self.assertEqual(reference['negative'], 'blurry')
        self.assertEqual(self.repo.artifact(selected['id'])['source'], 'generate')

    async def test_invalid_requests_leave_cursor_epoch_and_prefetch_unchanged(self):
        selected, _ = self.image(roam=True)
        not_liked, _ = self.image(liked=False)
        self.repo.roam_view({'artifact_id': selected['id'], 'viewed_at': 1})
        self.application.roam.save_options(anchors={'pinned_positive': ['keep this'],
            'excluded_positive': ['keep excluded'], 'pinned_canvas': {'width': 768, 'height': 1024},
            'preset_base_positive': []})
        before = self.application.roam.get(), self.repo.roam_view(), self.repo.counts()
        for payload in ({}, {'artifact_id': None}, {'artifact_id': ''}, {'artifact_id': 'x' * 101},
                        {'artifact_id': 'missing'}, {'artifact_id': not_liked['id']},
                        {'artifact_id': selected['id'], 'unexpected': True}):
            with self.subTest(payload=payload):
                response = await self.client.post('/api/roam/start', json=payload)
                self.assertIn(response.status, (400, 404))
                self.assertEqual((self.application.roam.get(), self.repo.roam_view(), self.repo.counts()), before)

    async def test_old_prompt_preparation_is_cancelled_without_pausing_the_new_epoch(self):
        selected, _ = self.image()
        old_epoch = self.application.roam.get()['epoch']
        async def old_preparation():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.repo.pause_roam(old_epoch, 'old preparation cancelled')
                raise
        preparation = asyncio.create_task(old_preparation())
        self.application._roam_preparation = preparation
        await asyncio.sleep(0)
        await self.start(selected['id'])
        self.assertTrue(preparation.cancelled())
        self.assertIsNone(self.application._roam_preparation)
        state = self.repo.ensure_roam(self.application.roam.get()['epoch'], selected['id'], 0)
        self.assertFalse(state['paused'])


if __name__ == '__main__':
    unittest.main()
