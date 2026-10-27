"""Pixel pools, API reuse, immutable task sizes and actual adapter requests."""
import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, patch

from backend.domain import BackendError, ValidationError
from backend.generation import validate_backend
from backend.generation.comfyui import ComfyBackend
from backend.generation.cloud import OpenAIBackend
from backend.generation.workflows import default_txt2img
from backend.store.sqlite import Repository
from tests.backend.application import test_natural_prompts as fixture
from tests.backend.application.test_app import configuration


SIZES = [{'width': 1024, 'height': 1024}, {'width': 768, 'height': 1024}, {'width': 1024, 'height': 768}]


def image_api(**fields):
    config = dict(configuration(), canvas_pool_id='mixed', **fields)
    config['workflow']['4'] = {'class_type': 'EmptyLatentImage', 'inputs': {'width': 832, 'height': 1216}}
    config['workflow']['other'] = {'class_type': 'Scale', 'inputs': {'width': 4096, 'height': 2048}}
    config['bindings'].update({key: {'node_id': '4', 'input': key} for key in ('width', 'height')})
    return config


class CanvasPoolTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.NaturalPromptTests.asyncSetUp
    asyncTearDown = fixture.NaturalPromptTests.asyncTearDown

    async def setup_pool(self, **fields):
        await self.app.save_canvas_pool('mixed', {'name': 'Mixed', 'sizes': SIZES})
        return await self.app.save_backend('local', image_api(**fields))

    async def enqueue(self):
        return await self.app.ensure_roam({'anchor_id': None, 'demand': True})

    async def test_pool_http_reuse_validation_and_reference_protection(self):
        response = await self.client.put('/api/canvas-pools/mixed', json={'name': 'Mixed', 'sizes': SIZES})
        self.assertEqual(response.status, 200)
        await self.app.save_backend('local', image_api())
        await self.app.save_backend('second', image_api())
        response = await self.client.get('/api/canvas-pools')
        self.assertEqual(len(await response.json()), 1)
        response = await self.client.delete('/api/canvas-pools/mixed', json={})
        self.assertEqual(response.status, 400)
        for sizes in ([], [SIZES[0], SIZES[0]], [{'width': True, 'height': 1024}], [{'width': 1.5, 'height': 1024}], [{'width': 0, 'height': 1024}], [{'width': 16385, 'height': 1024}]):
            response = await self.client.put('/api/canvas-pools/mixed', json={'name': 'Broken', 'sizes': sizes})
            self.assertEqual(response.status, 400)
        await self.app.save_backend('local', dict(image_api(), canvas_pool_id=''))
        await self.app.save_backend('second', dict(image_api(), canvas_pool_id=''))
        response = await self.client.delete('/api/canvas-pools/mixed', json={})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), [])

    async def test_roam_records_pixel_choice_and_preserves_it_after_pool_edit_and_restart(self):
        await self.setup_pool()
        with patch('backend.application.secrets.choice', return_value=SIZES[1]) as choose:
            first = (await self.enqueue())['job']
            self.assertEqual((first['width'], first['height']), (768, 1024))
            choose.assert_called_once_with(SIZES)
        repository = Repository(self.app.paths.database)
        self.assertEqual(repository.job(first['id'])['width'], 768)
        self.assertEqual(repository.job_backend(first['id'])['workflow']['4']['inputs']['width'], 832)
        updated = [{'width': 1280, 'height': 768}]
        await self.app.save_canvas_pool('mixed', {'name': 'Updated', 'sizes': updated})
        old = self.app.storage.job(first['id'])
        self.assertEqual((old['width'], old['height']), (768, 1024))
        self.assertEqual(self.app.storage.job_backend(first['id'])['canvas_pool_id'], 'mixed')
        second = (await self.enqueue())['job']
        self.assertEqual((second['width'], second['height']), (1280, 768))

    async def test_fixed_roam_and_generate_keep_api_size_while_pool_mode_filters_comfy_sizes(self):
        await self.setup_pool()
        response = await self.client.put('/api/settings/roam', json={'use_canvas_pool': False})
        self.assertEqual(response.status, 200)
        self.assertFalse((await response.json())['use_canvas_pool'])
        fixed = (await self.enqueue())['job']
        self.assertIsNone(fixed['width'])
        self.assertIsNone(fixed['height'])
        await self.app.roam_settings({'use_canvas_pool': True})
        await self.app.save_canvas_pool('mixed', {'name': 'Mixed', 'sizes': [{'width': 777, 'height': 999}, SIZES[2]]})
        mixed = (await self.enqueue())['job']
        self.assertEqual((mixed['width'], mixed['height']), (1024, 768))
        for _ in range(2):
            response = await self.client.post('/api/jobs', json={'backend_id': 'local', 'request_id': 'fixed-generate-request', 'positive': 'garden', 'negative': '', 'seed': -1})
            self.assertEqual(response.status, 202)
            generated = (await response.json())['job']
            self.assertIsNone(generated['width'])
        jobs = await self.app.list_jobs()
        self.assertEqual(sum(job['source'] == 'generate' for job in jobs), 1)
        with self.assertRaises(ValidationError):
            await self.app.save_canvas_pool('mixed', {'name': 'Invalid for linked API', 'sizes': [{'width': 777, 'height': 999}]})

    async def test_unrelated_pool_edits_and_renames_preserve_active_prefetch(self):
        await self.setup_pool()
        job = (await self.enqueue())['job']
        epoch = self.app.roam.get()['epoch']
        await self.app.save_canvas_pool('unused', {'name': 'Unused', 'sizes': SIZES})
        await self.app.save_canvas_pool('mixed', {'name': 'Renamed', 'sizes': SIZES})
        self.assertEqual(self.app.roam.get()['epoch'], epoch)
        self.assertEqual(self.app.storage.job(job['id'])['status'], 'queued')

    async def test_natural_language_roam_also_persists_dimensions(self):
        await self.setup_pool(prompt_type='natural_language')
        result = await self.enqueue()
        self.assertTrue(result['preparing_prompt'])
        await asyncio.wait_for(self.app._roam_preparation, 3)
        job = self.app.storage.jobs()[0]
        self.assertIn({'width': job['width'], 'height': job['height']}, SIZES)
        self.assertIn('A scene depicting', job['positive'])
        self.assertIn('source_prompts', job)

    async def test_pixel_pool_capabilities_and_unbound_workflow_validation(self):
        await self.app.save_canvas_pool('mixed', {'name': 'Mixed', 'sizes': SIZES})
        with self.assertRaises(BackendError):
            await self.app.save_backend('local', dict(configuration(), canvas_pool_id='mixed'))
        for kind in ('gemini', 'openai'):
            cloud = {'name': kind, 'kind': kind, 'model': 'mock-model', 'base_url': 'http://localhost:1', 'canvas_pool_id': 'mixed'}
            if kind == 'gemini':
                with self.assertRaises(BackendError):
                    await self.app.save_backend(kind, cloud)
            else:
                saved = await self.app.save_backend(kind, cloud)
                self.assertTrue(saved['capabilities']['dimensions'])
        default = validate_backend(dict(image_api(), id='default', **default_txt2img('model.safetensors')))
        self.assertEqual(default['bindings']['width'], {'node_id': '4', 'input': 'width'})
        invalid = image_api()
        invalid['bindings']['height'] = invalid['bindings']['width']
        with self.assertRaises(BackendError):
            validate_backend(invalid)
        with self.assertRaises(ValidationError):
            await self.app.roam_settings({'use_canvas_pool': 'true'})

    async def test_adapters_submit_exact_persisted_size_and_keep_fixed_workflow_unchanged(self):
        config = dict(image_api(), id='local')
        original = copy.deepcopy(config)
        backend = ComfyBackend(config, None)
        backend._json = AsyncMock(return_value={'prompt_id': 'remote'})
        plan = {'positive': 'garden', 'negative': '', 'seed': 42, 'width': 768, 'height': 1024}
        await backend.submit(plan, 'pixel-request')
        workflow = backend._json.call_args.kwargs['payload']['prompt']
        self.assertEqual(workflow['4']['inputs'], {'width': 768, 'height': 1024})
        self.assertEqual(workflow['other']['inputs'], original['workflow']['other']['inputs'])
        self.assertEqual(config, original)
        for dimensions in ({'width': 777, 'height': 1024}, {'width': 768, 'height': None}):
            backend._json.reset_mock()
            with self.assertRaises(BackendError):
                await backend.submit(dict(plan, **dimensions), 'invalid-request')
            backend._json.assert_not_awaited()
        await backend.submit(dict(plan, width=None, height=None), 'fixed-request')
        self.assertEqual(backend._json.call_args.kwargs['payload']['prompt']['4']['inputs'], original['workflow']['4']['inputs'])
        cloud = OpenAIBackend({'id': 'cloud', 'name': 'Mock', 'model': 'mock-model', 'size': '1024x1024'}, None)
        cloud._json = AsyncMock(return_value={'data': [{'url': 'http://localhost/image.png'}]})
        await cloud.submit(plan, 'cloud-size-request')
        self.assertEqual(cloud._json.call_args.args[2]['size'], '768x1024')
        self.assertNotIn('seed', cloud._json.call_args.args[2])
