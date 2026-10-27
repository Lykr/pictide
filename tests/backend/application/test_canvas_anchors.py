"""Canvas anchors share Roam freshness and durable task dimensions; no GPU."""
import asyncio
import unittest
from unittest.mock import patch

from backend.store.roam_settings import RoamSettings
from tests.backend.application import test_canvas_pools as fixtures


class CanvasAnchorTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CanvasPoolTests.asyncSetUp
    asyncTearDown = fixtures.CanvasPoolTests.asyncTearDown
    setup_pool = fixtures.CanvasPoolTests.setup_pool
    enqueue = fixtures.CanvasPoolTests.enqueue

    async def put(self, payload, status=200):
        response = await self.client.put('/api/settings/roam', json=payload)
        result = await response.json()
        self.assertEqual(response.status, status, result)
        return result

    async def test_pin_overrides_pool_and_fixed_mode_then_clear_restores_selection(self):
        await self.setup_pool()
        size = {'width': 896, 'height': 1152}
        saved = await self.put({'pinned_canvas': size, 'use_canvas_pool': False})
        self.assertEqual(saved['pinned_canvas'], size)
        with patch('backend.application.secrets.choice') as choose:
            job = (await self.enqueue())['job']
            self.assertEqual((job['width'], job['height']), (896, 1152))
            choose.assert_not_called()
        epoch = self.app.roam.get()['epoch']
        await self.put({'pinned_canvas': size})
        self.assertEqual(self.app.roam.get()['epoch'], epoch)
        await self.put({'prefetch_count': 2, 'backend_id': 'local'})
        self.assertEqual(RoamSettings(self.app.paths).get()['pinned_canvas'], size)
        await self.put({'pinned_canvas': None})
        fixed = (await self.enqueue())['job']
        self.assertIsNone(fixed['width'])
        await self.put({'use_canvas_pool': True})
        with patch('backend.application.secrets.choice', return_value=fixtures.SIZES[2]):
            mixed = (await self.enqueue())['job']
        self.assertEqual((mixed['width'], mixed['height']), (1024, 768))

    async def test_pin_invalidates_only_future_results_and_retains_image_metadata(self):
        await self.setup_pool()
        await self.put({'prefetch_count': 5})
        def finish(job):
            self.app.storage.complete(job['id'], [{'node_id': '9', 'index': 0, 'filename': 'neutral.png'}])
            return next(image for image in self.app.storage.artifacts(source='roam') if image['job_id'] == job['id'])
        first_job = (await self.enqueue())['job']
        current = finish(first_job)
        self.assertEqual(current['width'], first_job['width'])
        self.assertEqual(self.app.storage.artifact(current['id'])['height'], first_job['height'])
        self.app.storage.roam_view({'artifact_id': current['id'], 'viewed_at': 1})
        future = finish((await self.enqueue())['job'])
        queued = (await self.enqueue())['job']
        running = (await self.enqueue())['job']
        self.app.storage.claim_job(running['id'])
        self.app.storage.attach_prompt(running['id'], 'old')
        self.app.storage.update_job(running['id'], 'running')
        size = {'width': 896, 'height': 1152}
        await self.put({'pinned_canvas': size})
        self.assertEqual(self.app.storage.job(queued['id'])['status'], 'cancelled')
        self.app.storage.complete(running['id'], [{'node_id': '9', 'index': 0, 'filename': 'late.png'}])
        self.assertEqual([row['id'] for row in self.app.storage.artifacts(source='roam')], [current['id']])
        self.assertNotEqual(current['id'], future['id'])
        pinned = (await self.enqueue())['job']
        self.assertEqual((pinned['width'], pinned['height']), (896, 1152))
        epoch = self.app.roam.get()['epoch']
        await self.app.save_canvas_pool('mixed', {'name': 'Changed pool', 'sizes': [{'width': 1280, 'height': 768}]})
        self.assertEqual(self.app.roam.get()['epoch'], epoch)
        self.assertEqual(self.app.storage.job(pinned['id'])['status'], 'queued')

    async def test_invalid_or_unsupported_pin_is_rejected_without_mutating_settings(self):
        await self.setup_pool()
        epoch = self.app.roam.get()['epoch']
        invalid = [{}, {'width': 832}, {'width': 832, 'height': 1216, 'ratio': '2:3'},
                   {'width': True, 'height': 1024}, {'width': 832.0, 'height': 1216},
                   {'width': 0, 'height': 1024}, {'width': 16385, 'height': 1024},
                   {'width': 777, 'height': 1024}, '832x1216', []]
        for value in invalid:
            await self.put({'pinned_canvas': value}, status=400)
        self.assertEqual(self.app.roam.get()['epoch'], epoch)
        self.assertIsNone(self.app.roam.get()['pinned_canvas'])
        await self.app.save_backend('gemini', {'name': 'Unsupported', 'kind': 'gemini', 'base_url': 'http://localhost:1', 'model': 'test'})
        await self.put({'prefetch_count': 0, 'backend_id': 'gemini', 'pinned_canvas': {'width': 832, 'height': 1216}}, status=400)
        self.assertEqual(self.app.roam.get()['backend_id'], 'local')

    async def test_prompt_anchor_mode_does_not_lock_canvas_and_migration_preserves_state(self):
        await self.setup_pool()
        await self.put({'pinned_positive': ['garden'], 'prompt_mode': 'stay'})
        size = {'width': 832, 'height': 1216}
        await self.put({'pinned_canvas': size})
        await self.put({'playback_interval_seconds': 10})
        reloaded = RoamSettings(self.app.paths).get()
        self.assertEqual(reloaded['pinned_positive'], ['garden'])
        self.assertEqual(reloaded['pinned_canvas'], size)
        await self.put({'pinned_canvas': None})
        epoch = self.app.roam.get()['epoch']
        with self.app.roam.connect() as db:
            db.execute('ALTER TABLE roam_anchor_settings DROP COLUMN pinned_canvas')
        migrated = RoamSettings(self.app.paths).get()
        self.assertIsNone(migrated['pinned_canvas'])
        self.assertEqual(migrated['epoch'], epoch)
        self.assertEqual(migrated['pinned_positive'], ['garden'])

    async def test_canvas_change_discards_inflight_text_then_persists_new_size(self):
        await self.setup_pool(prompt_type='natural_language')
        self.renderer.wait = asyncio.Event()
        await self.enqueue()
        await asyncio.wait_for(self.renderer.started.wait(), 3)
        pending = self.app._roam_preparation
        await self.put({'pinned_canvas': {'width': 896, 'height': 1152}})
        self.renderer.wait.set()
        await asyncio.wait_for(pending, 3)
        self.assertEqual(self.app.storage.jobs(), [])
        await self.enqueue()
        await asyncio.wait_for(self.app._roam_preparation, 3)
        job = self.app.storage.jobs()[0]
        self.assertEqual((job['width'], job['height']), (896, 1152))
        self.assertIn('A scene depicting', job['positive'])
