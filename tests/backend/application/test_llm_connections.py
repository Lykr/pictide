"""Connection ownership, backward compatibility and provider/session isolation."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.domain import ValidationError, ConflictError
from backend.store.prompting import PromptStore, LEGACY_ID
from tests.backend.application import test_natural_prompts as fixture
from tests.backend.application.test_app import configuration


class LLMConnectionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.NaturalPromptTests.asyncSetUp
    asyncTearDown = fixture.NaturalPromptTests.asyncTearDown

    async def test_named_connections_select_independently_and_protect_references(self):
        payload = {'name': 'Second LLM', 'kind': 'openai', 'base_url': 'http://localhost:2/v1', 'model': 'second', 'api_key': 'second-secret'}
        response = await self.client.put('/api/llm-apis/second', json=payload)
        self.assertEqual(response.status, 200)
        public = await response.json()
        self.assertNotIn('second-secret', json.dumps(public))
        self.assertEqual(len(public), 2)
        image_api = dict(configuration(), id='second-image', prompt_type='natural_language', llm_id='second')
        await self.app.save_backend('second-image', image_api)
        observed = []
        original = self.renderer.render

        async def render(config, *args, **kwargs):
            observed.append(config['model'])
            return await original(config, *args, **kwargs)

        self.renderer.render = render
        for identifier in ('local', 'second-image'):
            await self.app.prompting.prepare(identifier, self.app.storage.backend(identifier), {'positive': 'garden', 'negative': ''})
        self.assertEqual(observed, ['test', 'second'])
        deleted = await self.client.delete('/api/llm-apis/second', json={})
        self.assertEqual(deleted.status, 400)
        await self.app.save_backend('second-image', dict(image_api, prompt_type='danbooru'))
        deleted = await self.client.delete('/api/llm-apis/second', json={})
        self.assertEqual(deleted.status, 200)
        with self.assertRaises(ValidationError):
            await self.app.save_backend('second-image', image_api)

    async def test_legacy_migration_is_once_and_preserves_revision(self):
        with self.app.storage.connection() as db:
            db.execute('DELETE FROM llm_connections')
            config = {'base_url': 'http://localhost:1/v1', 'model': 'old', 'api_key': 'keep-secret'}
            db.execute('INSERT INTO prompt_settings VALUES (1,?,?)', ('original-revision', json.dumps(config)))
        store = PromptStore(self.app.storage)
        migrated = store.settings()
        self.assertEqual(migrated['revision'], 'original-revision')
        self.assertEqual(migrated['api_key'], 'keep-secret')
        store.save_connection(dict(migrated, name='Renamed'))
        self.assertEqual(PromptStore(self.app.storage).settings()['name'], 'Renamed')
        self.assertEqual(len(store.connections()), 1)
        self.assertEqual(store.settings()['id'], LEGACY_ID)

    async def test_selected_connection_edit_invalidates_inflight_result(self):
        await self.app.save_llm('second', {'name': 'Second', 'kind': 'openai', 'base_url': 'http://localhost:2/v1', 'model': 'second'})
        backend = dict(configuration(), llm_id='second', prompt_type='natural_language')
        self.renderer.wait = asyncio.Event()
        task = asyncio.create_task(self.app.prompting.prepare('inflight', backend, {'positive': 'garden', 'negative': ''}))
        await self.renderer.started.wait()
        await self.app.save_llm('second', {'name': 'Second', 'kind': 'openai', 'base_url': 'http://localhost:2/v1', 'model': 'changed'})
        self.renderer.wait.set()
        with self.assertRaises(ConflictError):
            await task

    async def test_chatgpt_config_masks_tokens_and_local_only_sign_in(self):
        await self.app.save_llm('account', {'name': 'Personal', 'kind': 'chatgpt', 'model': ''})
        with patch.object(self.app.chatgpt, 'start', return_value={'authorization_url': 'https://auth.openai.com/example'}) as start:
            response = await self.client.post('/api/llm-apis/account/sign-in', json={})
            self.assertEqual(response.status, 200)
            start.assert_awaited_once()
            blocked = await self.client.post('/api/llm-apis/account/sign-in', json={}, headers={'Origin': 'https://unrelated.example'})
            self.assertEqual(blocked.status, 403)
            start.assert_awaited_once()
        from backend.host import llm_action
        for remote, host in [('192.168.1.2', '127.0.0.1:8189'), ('127.0.0.1', '192.168.1.1:8189')]:
            request = SimpleNamespace(match_info={'operation': 'sign-in'}, remote=remote, host=host)
            with self.assertRaises(ValidationError):
                await llm_action(request)
        response = await self.client.get('/api/llm-apis/account/status')
        self.assertEqual(await response.json(), {'status': 'idle'})
        with self.assertRaises(ValidationError):
            await self.app.save_llm('account', {'name': 'Changed', 'kind': 'openai'})
