"""Official OAuth semantics with signed local identities and no provider requests."""
import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import aiohttp
import jwt
from aiohttp import web
from aiohttp.test_utils import TestServer
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.domain import ValidationError
from backend.prompting.chatgpt import ChatGPTClient, ISSUER, TOKEN_URL, PERMISSION, read_response, remote_error
from backend.store.chatgpt import ChatGPTCredentials


class ChatGPTTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.credentials = ChatGPTCredentials(Path(self.temp.name))
        self.changed = AsyncMock()
        self.client = ChatGPTClient(self.credentials, self.changed)
        self.addAsyncCleanup(self.client.close)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = dict(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key())), kid='fixture')

    def identity(self, nonce, **extra):
        return jwt.encode(dict(iss=ISSUER, sub='account-a', aud='oaiapp_fixture', exp=time.time()+60, nonce=nonce, **extra),
                          self.key, algorithm='RS256', headers={'kid': 'fixture'})

    def tokens(self, **extra):
        return dict(access_token='secret-access', refresh_token='secret-refresh', token_type='Bearer',
                    expires_in=3600, scope=PERMISSION, **extra)

    async def seed(self, **extra):
        async with self.credentials.transaction() as document:
            record = self.client.token_record(self.tokens())
            document['accounts']['personal'] = dict(record, client_id='oaiapp_fixture', subject='account-a', **extra)
            self.credentials.write(document)

    async def test_registration_pkce_state_signature_and_replay(self):
        result = await self.client.start('personal')
        query = parse_qs(urlsplit(result['authorization_url']).query)
        attempt = self.client.attempts['personal']
        self.assertEqual(query['client_id'], ['dynamic_agent_client'])
        self.assertEqual(query['agent_name_hint'], ['Pictide'])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertNotIn(attempt['verifier'], result['authorization_url'])
        async def request(method, url, **options):
            if url == TOKEN_URL:
                self.assertEqual(options['data']['client_id'], 'oaiapp_fixture')
                self.assertEqual(options['data']['redirect_uri'], attempt['redirect_uri'])
                self.assertEqual(options['data']['code_verifier'], attempt['verifier'])
                return 200, self.tokens(id_token=self.identity(attempt['nonce']))
            return 200, {'keys': [self.jwk]}
        self.client.request = AsyncMock(side_effect=request)
        async with aiohttp.ClientSession() as session:
            params = dict(state='wrong', code='fixture-code', client_id='oaiapp_fixture')
            async with session.get(attempt['redirect_uri'], params=params) as response:
                self.assertEqual(response.status, 400)
            self.client.request.assert_not_awaited()
            params['state'] = attempt['state']
            async with session.get(attempt['redirect_uri'], params=params) as response:
                self.assertEqual(response.status, 200)
                self.assertNotIn('secret', await response.text())
            async with session.get(attempt['redirect_uri'], params=params) as response:
                self.assertEqual(response.status, 400)
        self.assertEqual(self.client.status('personal')['status'], 'connected')
        self.changed.assert_awaited_once_with('personal')
        accounts = await self.client.accounts()
        self.assertTrue(accounts['personal']['plan_enabled'])
        self.assertNotIn('secret', json.dumps(accounts))
        again = parse_qs(urlsplit((await self.client.start('personal'))['authorization_url']).query)
        self.assertEqual(again['client_id'], ['oaiapp_fixture'])
        self.assertEqual(query['ext_agent_host_id'], again['ext_agent_host_id'])
        self.assertNotIn('agent_name_hint', again)

    async def test_identity_wrong_nonce_audience_and_signature_are_rejected(self):
        self.client.request = AsyncMock(return_value=(200, {'keys': [self.jwk]}))
        with self.assertRaises(ValidationError):
            await self.client.validate_identity(self.identity('wrong'), 'oaiapp_fixture', 'expected')
        with self.assertRaises(jwt.InvalidAudienceError):
            await self.client.validate_identity(self.identity('expected'), 'other-client', 'expected')
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode({'iss': ISSUER, 'sub': 'account-a', 'aud': 'oaiapp_fixture', 'exp': time.time()+60, 'nonce': 'expected'}, wrong_key, algorithm='RS256', headers={'kid': 'fixture'})
        with self.assertRaises(jwt.InvalidSignatureError):
            await self.client.validate_identity(forged, 'oaiapp_fixture', 'expected')

    async def test_refresh_is_serialized_and_rotation_persisted(self):
        await self.seed()
        async with self.credentials.transaction() as document:
            document['accounts']['personal']['expires_at'] = 0
            self.credentials.write(document)
        self.client.request = AsyncMock(return_value=(200, self.tokens()))
        self.assertEqual(await asyncio.gather(*[self.client.access_token('personal') for _ in range(3)]), ['secret-access']*3)
        self.client.request.assert_awaited_once()
        record = self.credentials.read()['accounts']['personal']
        self.assertGreater(record['expires_at'], time.time())

    async def test_denied_scope_and_terminal_refresh_never_fall_back(self):
        await self.seed()
        async with self.credentials.transaction() as document:
            document['accounts']['personal']['scopes'] = ['openid']
            self.credentials.write(document)
        with self.assertRaisesRegex(ValidationError, 'not enabled'):
            await self.client.access_token('personal')
        async with self.credentials.transaction() as document:
            document['accounts']['personal']['expires_at'] = 0
            self.credentials.write(document)
        self.client.request = AsyncMock(return_value=(400, {'error': 'invalid_grant'}))
        with self.assertRaises(ValidationError):
            await self.client.access_token('personal')
        record = self.credentials.read()['accounts']['personal']
        self.assertEqual(record['client_id'], 'oaiapp_fixture')
        self.assertNotIn('refresh_token', record)

    async def test_models_and_disconnect_retain_registration(self):
        await self.seed()
        self.client.request = AsyncMock(return_value=(200, {'models': [
            {'slug': 'hidden', 'visibility': 'hide'}, {'slug': 'shown', 'display_name': 'Shown', 'visibility': 'list'}]}))
        self.assertEqual(await self.client.models('personal'), [{'value': 'shown', 'label': 'Shown'}])
        self.client.request = AsyncMock(side_effect=ValidationError('offline'))
        self.assertFalse(await self.client.disconnect('personal'))
        record = self.credentials.read()['accounts']['personal']
        self.assertEqual(record['client_id'], 'oaiapp_fixture')
        self.assertNotIn('access_token', record)

    async def test_sse_requires_completed_and_rejects_late_failure(self):
        class Stream:
            def __init__(self, events): self.raw = b''.join(b'data: '+json.dumps(event).encode()+b'\r\n\r\n' for event in events)
            async def iter_chunked(self, size):
                for i in range(0, len(self.raw), 7): yield self.raw[i:i+7]
        delta = {'type': 'response.output_text.delta', 'delta': '{"positive":"partial"}'}
        with self.assertRaises(ValidationError):
            await read_response(Stream([delta]))
        with self.assertRaisesRegex(ValidationError, 'usage limit'):
            await read_response(Stream([delta, {'type': 'response.failed', 'response': {'error': {'code': 'subscription_sharing_usage_limit_exceeded'}}}]))
        result = {'positive': 'A quiet garden.', 'negative': ''}
        completed = {'type': 'response.completed', 'response': {'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(result)}]}]}}
        self.assertEqual(await read_response(Stream([delta, completed])), result)
        text_done = {'type': 'response.output_text.done', 'output_index': 1, 'content_index': 0,
                     'text': json.dumps(result)}
        part_done = {'type': 'response.content_part.done', 'output_index': 1, 'content_index': 0,
                     'part': {'type': 'output_text', 'text': json.dumps(result)}}
        item_done = {'type': 'response.output_item.done', 'output_index': 1,
                     'item': {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(result)}]}}
        empty_completed = {'type': 'response.completed', 'response': {'status': 'completed', 'output': []}}
        for done in (text_done, part_done, item_done):
            self.assertEqual(await read_response(Stream([delta, done, empty_completed])), result)
            with self.assertRaisesRegex(ValidationError, 'ended before completion'):
                await read_response(Stream([done]))
            with self.assertRaisesRegex(ValidationError, 'usage limit'):
                await read_response(Stream([done, {'type': 'response.failed', 'response': {
                    'error': {'code': 'subscription_sharing_usage_limit_exceeded'}}}]))
        self.assertEqual(await read_response(Stream([text_done, part_done, item_done, empty_completed])), result)
        with self.assertRaisesRegex(ValidationError, 'without prompt text'):
            await read_response(Stream([empty_completed]))
        with self.assertRaisesRegex(ValidationError, 'invalid prompt JSON'):
            await read_response(Stream([{**text_done, 'text': 'not JSON'}, empty_completed]))

    async def test_responses_transport_uses_plan_without_image_or_paid_fallback(self):
        await self.seed()
        requests = []
        result = {'positive': 'A quiet garden.', 'negative': ''}
        async def inference(request):
            payload = await request.json()
            requests.append(payload)
            self.assertEqual(request.headers['Authorization'], 'Bearer secret-access')
            self.assertIs(payload['store'], False)
            self.assertIs(payload['stream'], True)
            self.assertIsInstance(payload['input'], list)
            self.assertEqual(payload['model'], 'fixture-model')
            self.assertNotIn('messages', payload)
            format = payload['text']['format']
            if format.get('type') != 'json_schema':
                return web.json_response({'error': {'code': 'unsupported_value', 'param': 'text.format.type'}}, status=400)
            self.assertIs(format['strict'], True)
            schema = format['schema']
            self.assertEqual(set(schema['required']), {'positive', 'negative'})
            self.assertEqual(schema['properties'], {'positive': {'type': 'string'}, 'negative': {'type': 'string'}})
            self.assertIs(schema['additionalProperties'], False)
            events = [
                {'type': 'response.output_text.done', 'output_index': 0, 'content_index': 0, 'text': json.dumps(result)},
                {'type': 'response.completed', 'response': {'status': 'completed', 'output': []}},
            ]
            return web.Response(text=''.join('data: '+json.dumps(event)+'\n\n' for event in events),
                                content_type='text/event-stream')
        app = web.Application()
        app.router.add_post('/responses', inference)
        server = TestServer(app)
        await server.start_server()
        self.addAsyncCleanup(server.close)
        with patch('backend.prompting.chatgpt.RESOURCE', str(server.make_url('/')).rstrip('/')):
            value = await self.client.render({'id':'personal','model':'fixture-model'}, 'Return JSON.', {'positive':'garden','negative':''})
        self.assertEqual(value, result)
        self.assertEqual(len(requests), 1)

    async def test_request_error_preserves_safe_diagnostics_without_retry_or_signout(self):
        await self.seed()
        calls = 0
        async def rejected(request):
            nonlocal calls
            calls += 1
            return web.json_response({'error': {
                'code': 'subscription_sharing_unsupported_capability', 'param': 'text.format',
                'message': 'private prompt and secret-access must not be exposed'}},
                status=400, headers={'x-request-id': 'req_fixture'})
        app = web.Application()
        app.router.add_post('/responses', rejected)
        server = TestServer(app)
        await server.start_server()
        self.addAsyncCleanup(server.close)
        with patch('backend.prompting.chatgpt.RESOURCE', str(server.make_url('/')).rstrip('/')):
            with self.assertLogs('backend.prompting.chatgpt', level='WARNING') as logs:
                with self.assertRaises(ValidationError) as raised:
                    await self.client.render({'id': 'personal', 'model': 'fixture-model'}, 'Return JSON.', {})
        message = str(raised.exception)
        self.assertIn('HTTP 400', message)
        self.assertIn('subscription_sharing_unsupported_capability', message)
        self.assertIn('text.format', message)
        self.assertNotIn('sign in again', message.lower())
        self.assertIn('req_fixture', '\n'.join(logs.output))
        self.assertNotIn('secret-access', message + str(logs.output))
        self.assertNotIn('private prompt', message + str(logs.output))
        self.assertEqual(calls, 1)
        self.assertEqual(self.credentials.read()['accounts']['personal']['access_token'], 'secret-access')

    def test_unknown_error_shapes_do_not_echo_bodies_or_ask_for_signin_on_400(self):
        cases = [None, {'detail': 'secret-access'}, {'error': ['secret-access']},
                 {'error': {'code': [], 'param': {'private': 'prompt'}, 'message': 'secret-access'}},
                 {'error': {'code': 'Bearer secret-access', 'param': 'private prompt'}}]
        for body in cases:
            with self.subTest(body=body), self.assertLogs('backend.prompting.chatgpt', level='WARNING') as logs:
                message = str(remote_error(400, body, 'Bearer secret-access'))
            self.assertIn('HTTP 400', message)
            self.assertNotIn('secret-access', message + str(logs.output))
            self.assertNotIn('private prompt', message + str(logs.output))
            self.assertNotIn('sign in again', message.lower())
