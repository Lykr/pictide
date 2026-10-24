"""Prompt conversion boundaries, historical semantics and explicit request replay."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from backend.host import APPLICATION, create_app
from backend.prompting import PromptRenderer
from backend.prompt_preparation import PromptPreparation
from backend.store.prompting import PromptStore
from tests.backend.application.test_app import FakeBackend, configuration
from tests.backend.candidate.test_candidate_libraries import vocabulary
from backend.recommendation.service import RecommendationService
from tests.backend.recommendation.test_recommendation_application import CPUEncoder


class RecordingRenderer:
    def __init__(self):
        self.calls = []
        self.wait = None
        self.started = asyncio.Event()
        self.failure = False

    async def render(self, config, candidate, **options):
        self.calls.append((candidate, options))
        self.started.set()
        if self.wait:
            await self.wait.wait()
        if self.failure:
            raise ValueError('failed conversion')
        return {'positive': f'A scene depicting {candidate["positive"]}.',
                'negative': 'Avoid blur.' if options['negative_channel'] else ''}


class NaturalPromptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        vocabulary(self.root / 'libraries/neutral.sqlite3')
        (self.root / 'static').mkdir()
        with patch('backend.host.STATIC', self.root / 'static'):
            host = create_app(self.root, lambda config, session: FakeBackend())
        self.app = host[APPLICATION]
        self.client = TestClient(TestServer(host))
        await self.client.start_server()
        await self.app.tasks.stop()
        self.app.recommendation = RecommendationService(self.app.recommendation_store, CPUEncoder())
        self.app.storage.save_backend(dict(configuration(), id='local', prompt_type='natural_language'))
        self.renderer = RecordingRenderer()
        self.app.prompting.renderer = self.renderer
        await self.app.prompt_settings({'base_url': 'http://127.0.0.1:1/v1', 'model': 'test', 'api_key': 'text-secret'})
        self.preset = self.app.candidates.save_preset({'name': 'Neutral', 'document': {
            'base_positive': [], 'base_negative': [], 'min_tags': 2, 'max_tags': 2,
            'pmi_threshold': 0, 'min_cooccurrence': 10, 'change_budget': 2}})
        await self.app.roam_settings({'prefetch_count': 2, 'backend_id': 'local', 'preset_id': self.preset['id']})

    async def asyncTearDown(self):
        await self.client.close()

    async def post(self, path, payload, status=None):
        status = status or (202 if path == '/api/jobs' else 200)
        response = await self.client.post(path, json=payload)
        data = await response.json()
        self.assertEqual(response.status, status, data)
        return data

    async def roam(self):
        result = await self.app.ensure_roam({'anchor_id': None})
        self.assertTrue(result.get('preparing_prompt'), result)
        await asyncio.wait_for(self.app._roam_preparation, 3)
        return self.app.storage.jobs()[0]

    def finish(self, job):
        self.app.storage.complete(job['id'], [{'node_id': '9', 'index': 0, 'filename': 'neutral.png'}])
        return next(a for a in self.app.storage.artifacts() if a['job_id'] == job['id'])

    async def test_preview_is_reused_for_batch_and_restart_replay(self):
        preview = await self.post('/api/candidate/generate', {'preset_id': self.preset['id'], 'backend_id': 'local'})
        self.assertEqual(len(self.renderer.calls), 1)
        fields = dict(backend_id='local', request_id='preview-generation', seed=-1, count=2, repetitions=1,
                      positive=preview['positive'], negative=preview['negative'], preparation_id=preview['rendered']['preparation_id'])
        result = await self.post('/api/jobs', fields)
        self.assertEqual(len(result['jobs']), 2)
        self.assertEqual({j['positive'] for j in result['jobs']}, {preview['rendered']['positive']})
        self.assertEqual(len(self.renderer.calls), 1)
        self.app.prompting = PromptPreparation(PromptStore(self.app.storage))
        repeated = await self.post('/api/jobs', fields)
        self.assertEqual([j['id'] for j in repeated['jobs']], [j['id'] for j in result['jobs']])
        image = self.finish(result['jobs'][0])
        prompts = await self.app.prompts(image['id'])
        self.assertEqual(prompts['positive'], preview['rendered']['positive'])
        self.assertEqual(prompts['source_prompts']['positive'], preview['positive'])
        self.app.storage.rate(image['id'], 1)
        self.assertEqual(self.app.storage.liked_positive_prompts(), [preview['positive']])
        tag = preview['positive'].split(',')[0].strip()
        self.assertEqual(self.app.storage.artifact_page(liked=True, tags=(tag,))['total'], 1)

    async def test_stay_skips_llm_and_feedback_uses_semantic_snapshot(self):
        job = await self.roam()
        image = self.finish(job)
        self.app.storage.roam_view({'artifact_id': image['id'], 'viewed_at': 1})
        self.app.storage.rate(image['id'], 1)
        snapshot = self.app.storage.roam_snapshot(job['id'])
        scored = self.app._image_score_candidate(image, snapshot)
        self.assertEqual(scored.positive, snapshot['positive'])
        self.assertNotEqual(scored.positive, image['positive'])
        with self.app.storage.connection() as db:
            event = json.loads(db.execute('SELECT candidate FROM recommendation_events').fetchone()[0])
        self.assertEqual(event['positive'], snapshot['positive'])
        await self.app.roam_settings({'prompt_mode': 'stay'})
        second = await self.roam()
        self.assertEqual(len(self.renderer.calls), 1)
        self.assertEqual(second['positive'], job['positive'])
        self.assertNotEqual(second['request_id'], job['request_id'])

    async def test_along_context_and_random_isolation(self):
        first = self.finish(await self.roam())
        self.app.storage.roam_view({'artifact_id': first['id'], 'viewed_at': 1})
        await self.app.roam_settings({'prompt_mode': 'along'})
        # Force a different complete combination to exercise an actual conversion.
        original = self.app._roam_candidate
        def changed(context):
            chosen, snapshot = original(context)
            snapshot['positive'] += ', sunlight'
            snapshot['terms'].append({'text': 'sunlight', 'channel': 'positive'})
            return chosen, snapshot
        self.app._roam_candidate = changed
        await self.roam()
        options = self.renderer.calls[-1][1]
        self.assertEqual(options['mode'], 'along')
        self.assertEqual(options['previous']['prompt']['positive'], first['positive'])
        await self.app.roam_settings({'prompt_mode': 'random'})
        await self.roam()
        self.assertEqual(self.renderer.calls[-1][1]['mode'], 'random')
        self.assertIsNone(self.renderer.calls[-1][1]['previous'])

    async def test_settings_change_during_conversion_discards_late_result(self):
        self.renderer.wait = asyncio.Event()
        await self.app.ensure_roam({'anchor_id': None})
        await asyncio.wait_for(self.renderer.started.wait(), 2)
        repeated = await self.app.ensure_roam({'anchor_id': None})
        self.assertTrue(repeated['preparing_prompt'])
        self.assertEqual(len(self.renderer.calls), 1)
        await asyncio.wait_for(self.app.roam_settings({'prompt_mode': 'along'}), 2)
        self.renderer.wait.set()
        await self.app._roam_preparation
        self.assertEqual(self.app.storage.jobs(), [])

    async def test_failed_conversion_pauses_without_silent_retry(self):
        self.renderer.failure = True
        await self.app.ensure_roam({'anchor_id': None})
        await self.app._roam_preparation
        self.assertTrue((await self.app.ensure_roam({'anchor_id': None}))['paused'])
        self.assertEqual(len(self.renderer.calls), 1)
        self.assertEqual(self.app.storage.jobs(), [])

    async def test_settings_secrets_stale_preview_and_danbooru(self):
        public = await self.app.prompt_settings()
        self.assertTrue(public['has_api_key'])
        self.assertNotIn('text-secret', json.dumps(public))
        preview = await self.post('/api/candidate/generate', {'preset_id': self.preset['id'], 'backend_id': 'local'})
        await self.app.prompt_settings({'model': 'different'})
        fields = dict(backend_id='local', request_id='stale-preview', positive=preview['positive'], negative=preview['negative'],
                      preparation_id=preview['rendered']['preparation_id'])
        await self.post('/api/jobs', fields, 409)
        self.app.storage.save_backend(dict(configuration(), id='local'))
        await self.post('/api/jobs', dict(fields, request_id='old-tags-request', preparation_id=None))
        self.assertEqual(len(self.renderer.calls), 1)

    async def test_cloud_constraints_are_converted_before_generation_validation(self):
        self.app.storage.save_backend({'id': 'cloud', 'name': 'Cloud', 'kind': 'openai', 'model': 'image-test',
            'base_url': 'http://127.0.0.1:1/v1', 'prompt_type': 'natural_language'})
        result = await self.post('/api/jobs', {'backend_id': 'cloud', 'request_id': 'cloud-natural', 'positive': 'forest', 'negative': 'blurry'})
        self.assertEqual(result['job']['negative'], '')
        self.assertEqual(result['job']['source_prompts']['negative'], 'blurry')
        self.assertFalse(self.renderer.calls[-1][1]['negative_channel'])

    async def test_partial_batch_retry_retains_selection_and_completed_conversion(self):
        render = self.renderer.render
        fail = True
        async def interrupted(*args, **kwargs):
            if fail and len(self.renderer.calls) == 1:
                raise ValueError('interrupted second round')
            return await render(*args, **kwargs)
        self.renderer.render = interrupted
        fields = dict(backend_id='local', request_id='partial-batch', repetitions=2,
                      candidate={'preset_id': self.preset['id'], 'mode': 'random_each_run'})
        with self.assertRaisesRegex(ValueError, 'interrupted'):
            await self.app.submit_job(fields)
        self.assertEqual(self.app.storage.jobs(), [])
        selected = self.app.prompting.store.get('batch-partial-batch')['document']['rounds']
        fail = False
        with patch.object(self.app.candidates, 'prepare_rounds', side_effect=AssertionError('must not redraw')):
            result = await self.app.submit_job(fields)
        self.assertEqual(len(self.renderer.calls), 2)
        self.assertEqual([j['source_prompts']['positive'] for j in result['jobs']], [s['positive'] for s in selected])

    async def test_llm_change_during_generation_does_not_enqueue(self):
        self.renderer.wait = asyncio.Event()
        task = asyncio.create_task(self.app.submit_job(dict(backend_id='local', request_id='changing-llm', positive='forest')))
        await asyncio.wait_for(self.renderer.started.wait(), 2)
        await self.app.prompt_settings({'model': 'new-text-model'})
        self.renderer.wait.set()
        with self.assertRaisesRegex(ValueError, 'settings changed'):
            await task
        self.assertEqual(self.app.storage.jobs(), [])

    async def test_restart_does_not_retry_uncertain_automatic_conversion(self):
        backend = self.app.storage.backend('local')
        tags = {'positive': 'forest', 'negative': ''}
        self.renderer.failure = True
        with self.assertRaises(ValueError):
            await self.app.prompting.prepare('interrupted-roam', backend, tags, automatic=True)
        restored = PromptPreparation(PromptStore(self.app.storage))
        restored.renderer = RecordingRenderer()
        with self.assertRaisesRegex(ValueError, 'interrupted LLM request'):
            await restored.prepare('interrupted-roam', backend, tags, automatic=True)
        self.assertEqual(restored.renderer.calls, [])
        await restored.prepare('interrupted-roam', backend, tags)
        self.assertEqual(len(restored.renderer.calls), 1)


class TextProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_shape_boundaries_and_invalid_result(self):
        calls = []
        invalid = False
        async def handler(request):
            calls.append((dict(request.headers), await request.json()))
            return web.json_response({'choices': [{'finish_reason': 'stop', 'message': {
                'content': 'not-json' if invalid else json.dumps({'positive': 'A forest in sunlight.', 'negative': ''})}}]})
        service = web.Application()
        service.router.add_post('/v1/chat/completions', handler)
        async with TestServer(service) as server:
            config = {'base_url': str(server.make_url('/v1')), 'api_key': 'test-secret', 'model': 'test-text'}
            renderer = PromptRenderer()
            result = await renderer.render(config, {'positive': 'forest, sunlight', 'negative': 'blur'}, negative_channel=False)
            self.assertEqual(result['positive'], 'A forest in sunlight.')
            headers, body = calls[0]
            self.assertEqual(headers['Authorization'], 'Bearer test-secret')
            self.assertEqual(body['response_format'], {'type': 'json_object'})
            self.assertFalse(json.loads(body['messages'][1]['content'])['negative_channel'])
            invalid = True
            with self.assertRaisesRegex(ValueError, 'invalid prompt JSON'):
                await renderer.render(config, {'positive': 'forest', 'negative': ''})
            self.assertEqual(len(calls), 2)
