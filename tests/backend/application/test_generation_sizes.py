"""Generate pixel choices use existing job snapshots and durable batch replay."""
import unittest
from backend.store.sqlite import Repository
from tests.backend.application import test_natural_prompts as fixture
from tests.backend.application.test_canvas_pools import image_api, SIZES


class GenerationSizeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.NaturalPromptTests.asyncSetUp
    asyncTearDown = fixture.NaturalPromptTests.asyncTearDown

    async def setup_api(self, natural=False):
        await self.app.save_canvas_pool('mixed', {'name': 'Mixed', 'sizes': SIZES})
        await self.app.save_backend('local', image_api(prompt_type='natural_language' if natural else 'danbooru'))

    async def submit(self, payload, status=202):
        response = await self.client.post('/api/jobs', json=payload)
        result = await response.json()
        self.assertEqual(response.status, status, result)
        return result

    async def test_generate_batch_sizes_survive_replay_and_config_changes(self):
        await self.setup_api()
        fields = {'backend_id': 'local', 'request_id': 'chosen-size-batch', 'positive': 'garden', 'negative': '',
                  'seed': -1, 'count': 2, 'repetitions': 2, 'width': 768, 'height': 1024}
        result = await self.submit(fields)
        self.assertEqual(len(result['jobs']), 4)
        self.assertTrue(all((job['width'], job['height']) == (768, 1024) for job in result['jobs']))
        await self.app.save_canvas_pool('mixed', {'name': 'Changed', 'sizes': [SIZES[0]]})
        self.app.storage.delete_backend('local')
        repeated = await self.submit(fields)
        self.assertEqual([job['id'] for job in result['jobs']], [job['id'] for job in repeated['jobs']])
        repository = Repository(self.app.storage.path)
        self.assertTrue(all(repository.job(job['id'])['width'] == 768 for job in result['jobs']))
        await self.submit(dict(fields, width=1024, height=768), status=409)
        self.assertEqual(len(repository.jobs()), 4)

    async def test_manual_legacy_batch_forwards_explicit_dimensions_to_task(self):
        await self.setup_api()
        result = await self.submit({'backend_id': 'local', 'request_id': 'legacy-size-batch',
            'positive': 'garden', 'seed': -1, 'count': 2, 'width': 1024, 'height': 768})
        self.assertTrue(all((job['width'], job['height']) == (1024, 768) for job in result['jobs']))
        for _ in range(2):
            await self.app.tasks.tick()
        self.assertTrue(all(self.app.storage.job(job['id'])['status'] == 'completed' for job in result['jobs']))

    async def test_natural_candidate_rounds_keep_the_selected_size(self):
        await self.setup_api(natural=True)
        result = await self.submit({'backend_id': 'local', 'request_id': 'natural-size-batch', 'seed': -1,
            'count': 2, 'repetitions': 2, 'width': 768, 'height': 1024,
            'candidate': {'preset_id': self.preset['id'], 'mode': 'random_each_run', 'seed': 0, 'max_steps': 100,
                          'sequence_step': 0, 'seed_control': 'fixed', 'step_control': 'increment'}})
        self.assertEqual(len(result['jobs']), 4)
        self.assertTrue(all(job['width'] == 768 and job['height'] == 1024 for job in result['jobs']))
        self.assertTrue(all('source_prompts' in job and 'A scene depicting' in job['positive'] for job in result['jobs']))

    async def test_invalid_sizes_are_rejected_before_llm_preparation_or_jobs(self):
        await self.setup_api(natural=True)
        fields = {'backend_id': 'local', 'request_id': 'invalid-size-batch', 'positive': 'garden', 'seed': -1, 'repetitions': 1}
        for dimensions in ({'width': 768}, {'height': 1024}, {'width': True, 'height': 1024},
                           {'width': 0, 'height': 1024}, {'width': 768, 'height': 16385},
                           {'width': 768.5, 'height': 1024}, {'width': 777, 'height': 1024},
                           {'width': None, 'height': None}):
            await self.submit(dict(fields, **dimensions), status=400)
        self.assertEqual(self.renderer.calls, [])
        self.assertEqual(self.app.storage.jobs(), [])
        await self.app.save_backend('gemini', {'name': 'Gemini', 'kind': 'gemini', 'base_url': 'http://localhost:1',
                                               'model': 'mock-model', 'prompt_type': 'natural_language'})
        await self.submit(dict(fields, backend_id='gemini', width=1024, height=1024), status=400)
        self.assertEqual(self.renderer.calls, [])

    async def test_openai_accepts_pixels_and_default_omits_the_override(self):
        await self.app.save_backend('cloud', {'name': 'Mock', 'kind': 'openai', 'base_url': 'http://localhost:1',
            'model': 'mock-model', 'size': '1024x1024'})
        fields = {'backend_id': 'cloud', 'request_id': 'cloud-size-batch', 'positive': 'garden', 'seed': -1, 'repetitions': 1}
        result = await self.submit(dict(fields, width=1536, height=1024))
        self.assertEqual((result['job']['width'], result['job']['height']), (1536, 1024))
        default = await self.submit(dict(fields, request_id='cloud-default-size'))
        self.assertIsNone(default['job']['width'])
        self.assertIsNone(default['job']['height'])
