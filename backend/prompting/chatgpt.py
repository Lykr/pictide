"""Official public-client ChatGPT sign-in and plan-backed Responses transport."""
import asyncio
import base64
import hashlib
import json
import secrets
import time
import uuid
from urllib.parse import urlencode, urlsplit

import aiohttp
from aiohttp import web
import jwt

from ..domain import ConflictError, ValidationError
from ..network import proxy_for_url, tls_context

ISSUER = 'https://auth.openai.com'
TOKEN_URL = ISSUER + '/api/accounts/oauth/token'
RESOURCE = 'https://api.openai.com/v1'
PERMISSION = 'chatgpt.tokens.use.direct'
SCOPES = 'openid profile email offline_access resource.invoke ' + PERMISSION
TERMINAL_REFRESH = {'invalid_grant', 'invalid_refresh_token', 'token_expired', 'refresh_token_expired',
                    'refresh_token_invalidated', 'refresh_token_reused'}


def public_account(record):
    return {'email': record.get('email', ''), 'connected': bool(record.get('access_token')),
            'plan_enabled': PERMISSION in record.get('scopes', []),
            'welcomed': record.get('welcomed', False)}


def remote_error(status, data):
    code = data.get('error', {}) if isinstance(data, dict) else {}
    code = code.get('code', '') if isinstance(code, dict) else code
    messages = {
        'subscription_sharing_usage_limit_exceeded': 'ChatGPT usage limit reached. Manage usage in ChatGPT settings.',
        'subscription_sharing_user_not_eligible': 'ChatGPT plan usage is unavailable for this account or workspace.',
        'subscription_sharing_usage_unavailable': 'ChatGPT usage is temporarily unavailable. Retry later.',
    }
    return ValidationError(messages.get(code, f'ChatGPT request failed (HTTP {status}). Check the connection or sign in again.'))


class ChatGPTClient:
    def __init__(self, credentials, on_connected):
        self.credentials = credentials
        self.on_connected = on_connected
        self.attempts = {}

    async def request(self, method, url, **kwargs):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.request(method, url, **kwargs, proxy=proxy_for_url(url),
                                           ssl=tls_context(), allow_redirects=False) as response:
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(16384):
                        raw.extend(chunk)
                        if len(raw) > 1024 * 1024:
                            raise ValidationError('ChatGPT response is too large.')
                    try:
                        data = json.loads(raw) if raw else {}
                    except ValueError:
                        raise ValidationError(f'Invalid ChatGPT response (HTTP {response.status}).') from None
                    return response.status, data
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise ValidationError('Unable to connect to ChatGPT. Check the network and retry.') from None

    async def accounts(self):
        async with self.credentials.transaction() as document:
            return {key: public_account(record) for key, record in document['accounts'].items()}

    async def start(self, identifier):
        await self.cancel(identifier)
        self.attempts = {key: value for key, value in self.attempts.items()
                         if value.get('runner') or time.time() < value['expires']}
        if sum(a['status'] == 'pending' for a in self.attempts.values()) >= 5:
            raise ValidationError('Finish an existing ChatGPT sign-in first.')
        async with self.credentials.transaction() as document:
            host = document.setdefault('host_id', 'urn:uuid:' + str(uuid.uuid4()))
            old = dict(document['accounts'].get(identifier, {}))
            self.credentials.write(document)
        verifier = secrets.token_urlsafe(48)
        attempt = {'status': 'pending', 'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32),
                   'verifier': verifier, 'client_id': old.get('client_id'), 'subject': old.get('subject'),
                   'expires': time.time() + 600, 'runner': None, 'timer': None}
        callback_app = web.Application()
        async def callback(request):
            return await self.callback(identifier, attempt, request)
        callback_app.router.add_get('/auth/callback', callback)
        runner = web.AppRunner(callback_app, access_log=None)
        await runner.setup()
        try:
            site = web.TCPSite(runner, '127.0.0.1', 0)
            await site.start()
            port = runner.addresses[0][1]
        except BaseException:
            await runner.cleanup()
            raise
        attempt['runner'] = runner
        attempt['redirect_uri'] = f'http://127.0.0.1:{port}/auth/callback'
        self.attempts[identifier] = attempt
        params = {'client_id': old.get('client_id') or 'dynamic_agent_client', 'ext_agent_host_id': host,
                  'response_type': 'code', 'redirect_uri': attempt['redirect_uri'], 'scope': SCOPES,
                  'resource': RESOURCE, 'state': attempt['state'], 'nonce': attempt['nonce'],
                  'code_challenge_method': 'S256',
                  'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
        if not old.get('client_id'):
            params['agent_name_hint'] = 'Pictide'
        else:
            if old.get('email'):
                params['login_hint'] = old['email']
            if PERMISSION not in old.get('scopes', []):
                params['prompt'] = 'consent'
        attempt['timer'] = asyncio.get_running_loop().call_later(600, lambda: asyncio.create_task(self.cancel(identifier, 'expired')))
        return {'authorization_url': ISSUER + '/api/accounts/authorize?' + urlencode(params)}

    async def cancel(self, identifier, status='cancelled'):
        attempt = self.attempts.get(identifier)
        if attempt:
            attempt['status'] = status
            if attempt['timer']:
                attempt['timer'].cancel()
            if attempt['runner']:
                runner, attempt['runner'] = attempt['runner'], None
                await runner.cleanup()

    def status(self, identifier):
        attempt = self.attempts.get(identifier, {})
        return {key: attempt[key] for key in ('status', 'error') if key in attempt} or {'status': 'idle'}

    async def callback(self, identifier, attempt, request):
        # Callback URLs and provider bodies never enter logs or the returned page.
        headers = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                   'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"}
        if (request.host != urlsplit(attempt['redirect_uri']).netloc or attempt['status'] != 'pending'
                or time.time() > attempt['expires']
                or any(len(request.query.getall(key, [])) > 1 for key in ('state', 'code', 'client_id', 'error'))
                or not secrets.compare_digest(request.query.get('state', ''), attempt['state'])):
            return web.Response(status=400, text='Invalid or expired sign-in. Return to Pictide and try again.', headers=headers)
        attempt['status'] = 'exchanging'  # Consume once before any awaits.
        try:
            if request.query.get('error'):
                raise ValidationError('ChatGPT sign-in was cancelled or declined.')
            client_id = request.query.get('client_id', attempt['client_id'])
            if not client_id or client_id == 'dynamic_agent_client' or len(client_id) > 256:
                raise ValidationError('ChatGPT registration did not complete.')
            if attempt['client_id'] and client_id != attempt['client_id']:
                raise ValidationError('ChatGPT registration changed. Start a new connection.')
            code = request.query.get('code')
            if not code or len(code) > 8192:
                raise ValidationError('ChatGPT authorization code is missing or invalid.')
            status, tokens = await self.request('POST', TOKEN_URL, data={
                'grant_type': 'authorization_code', 'client_id': client_id, 'code': code,
                'code_verifier': attempt['verifier'], 'redirect_uri': attempt['redirect_uri'], 'resource': RESOURCE})
            if status != 200:
                raise remote_error(status, tokens)
            identity = await self.validate_identity(tokens.get('id_token', ''), client_id, attempt['nonce'])
            if attempt['subject'] and identity['sub'] != attempt['subject']:
                raise ValidationError('A different ChatGPT account signed in. Add a separate LLM API instead.')
            record = self.token_record(tokens)
            record.update(client_id=client_id, subject=identity['sub'], email=identity.get('email', ''), issuer=ISSUER)
            async with self.credentials.transaction() as document:
                if attempt['status'] != 'exchanging':
                    raise ConflictError('ChatGPT sign-in was cancelled.')
                record['welcomed'] = document['accounts'].get(identifier, {}).get('welcomed', False)
                # Invalidate preparations before exposing the newly authenticated session.
                await self.on_connected(identifier)
                if attempt['status'] != 'exchanging':
                    raise ConflictError('ChatGPT sign-in was cancelled.')
                document['accounts'][identifier] = record
                self.credentials.write(document)
            attempt['status'] = 'connected'
            message = 'Connected. Return to Pictide to select a model. / 已连接，请返回 Pictide 选择模型。'
        except (ValidationError, ConflictError, ValueError, KeyError, TypeError, OSError, jwt.PyJWTError) as error:
            attempt['status'] = 'cancelled' if request.query.get('error') == 'access_denied' else 'failed'
            attempt['error'] = str(error) if isinstance(error, ValidationError) else 'ChatGPT sign-in could not be verified. Please sign in again.'
            message = 'Sign-in failed. Return to Pictide and try again. / 登录失败，请返回 Pictide 重试。'
        finally:
            attempt['timer'].cancel()
            asyncio.get_running_loop().call_later(.2, lambda: asyncio.create_task(self._close_attempt(attempt)))
        return web.Response(text=message, headers=headers)

    async def _close_attempt(self, attempt):
        if attempt.get('runner'):
            runner, attempt['runner'] = attempt['runner'], None
            await runner.cleanup()
        for key in ('state', 'nonce', 'verifier'):
            attempt.pop(key, None)

    async def validate_identity(self, token, client_id, nonce):
        status, jwks = await self.request('GET', ISSUER + '/.well-known/jwks.json')
        if status != 200:
            raise remote_error(status, jwks)
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256':
            raise ValidationError('Unsupported ChatGPT identity signature.')
        keys = [key for key in jwks.get('keys', []) if key.get('kid') == header.get('kid') and key.get('kty') == 'RSA']
        if len(keys) != 1:
            raise ValidationError('ChatGPT identity signing key is unavailable.')
        identity = jwt.decode(token, jwt.PyJWK(keys[0]).key, algorithms=['RS256'], audience=client_id,
                              issuer=ISSUER, options={'require': ['iss', 'sub', 'aud', 'exp', 'nonce']})
        if (identity.get('azp', client_id) != client_id or
                isinstance(identity['aud'], list) and len(identity['aud']) > 1 and identity.get('azp') != client_id):
            raise ValidationError('ChatGPT identity has a different authorized client.')
        if not isinstance(identity['sub'], str) or not identity['sub'] or identity.get('nonce') != nonce:
            raise ValidationError('ChatGPT identity did not match the sign-in attempt.')
        if not isinstance(identity.get('email', ''), str):
            identity['email'] = ''
        return identity

    @staticmethod
    def token_record(tokens, previous=None):
        record = dict(previous or {})
        if not isinstance(tokens, dict) or not isinstance(tokens.get('access_token'), str) or not tokens['access_token']:
            raise ValidationError('ChatGPT returned invalid credentials.')
        if not isinstance(tokens.get('token_type'), str) or tokens['token_type'].lower() != 'bearer':
            raise ValidationError('Unsupported ChatGPT token type.')
        if any(not isinstance(tokens[key], str) or len(tokens[key]) > 65536
               for key in ('access_token', 'refresh_token', 'id_token', 'scope') if key in tokens):
            raise ValidationError('ChatGPT returned invalid credentials.')
        expires = tokens.get('expires_in')
        if not isinstance(expires, (float, int)) or not 0 < expires <= 365 * 86400:
            raise ValidationError('ChatGPT returned invalid token expiry.')
        record.update({key: tokens[key] for key in ('access_token', 'refresh_token', 'id_token') if key in tokens})
        record['expires_at'] = time.time() + expires
        record['scopes'] = tokens['scope'].split() if 'scope' in tokens else record.get('scopes', [])
        return record

    async def access_token(self, identifier):
        async with self.credentials.transaction() as document:
            record = document['accounts'].get(identifier, {})
            if not record.get('access_token'):
                raise ValidationError('Sign in to ChatGPT in LLM API settings.')
            if record.get('expires_at', 0) <= time.time() + 60:
                if not record.get('refresh_token'):
                    raise ValidationError('ChatGPT sign-in expired. Sign in again.')
                status, tokens = await self.request('POST', TOKEN_URL, data={'grant_type': 'refresh_token',
                    'client_id': record['client_id'], 'refresh_token': record['refresh_token'], 'resource': RESOURCE})
                if status != 200:
                    error = tokens.get('error') if isinstance(tokens, dict) else ''
                    if isinstance(error, dict):
                        error = error.get('code')
                    if error in TERMINAL_REFRESH:
                        for key in ('access_token', 'refresh_token', 'id_token'):
                            record.pop(key, None)
                        self.credentials.write(document)
                    raise remote_error(status, tokens)
                record = self.token_record(tokens, record)
                document['accounts'][identifier] = record
                self.credentials.write(document)
            if PERMISSION not in record.get('scopes', []):
                raise ValidationError('ChatGPT plan usage is not enabled. Authorize it in LLM API settings.')
            return record['access_token']

    async def models(self, identifier):
        token = await self.access_token(identifier)
        status, data = await self.request('GET', RESOURCE + '/models', headers={'Authorization': 'Bearer ' + token})
        if status != 200:
            raise remote_error(status, data)
        return [{'value': row['slug'], 'label': row.get('display_name', row['slug'])}
                for row in data.get('models', []) if row.get('visibility') == 'list' and isinstance(row.get('slug'), str)]

    async def disconnect(self, identifier):
        await self.cancel(identifier)
        confirmed = True
        async with self.credentials.transaction() as document:
            record = document['accounts'].get(identifier, {})
            if record.get('refresh_token'):
                try:
                    status, metadata = await self.request('GET', ISSUER + '/.well-known/openid-configuration')
                    url = metadata.get('revocation_endpoint', '')
                    if status != 200 or not url.startswith(ISSUER + '/'):
                        raise ValidationError('Revocation endpoint unavailable.')
                    for delay in (0, .5):
                        if delay:
                            await asyncio.sleep(delay)
                        status, _ = await self.request('POST', url, data={'token': record['refresh_token'],
                            'token_type_hint': 'refresh_token', 'client_id': record['client_id']})
                        if status == 200 or status < 500:
                            break
                    confirmed = status == 200
                except ValidationError:
                    confirmed = False
            for key in ('access_token', 'refresh_token', 'id_token'):
                record.pop(key, None)
            self.credentials.write(document)
        return confirmed

    async def welcome(self, identifier):
        async with self.credentials.transaction() as document:
            record = document['accounts'].get(identifier)
            if record:
                record['welcomed'] = True
                self.credentials.write(document)

    async def render(self, config, instructions, data):
        token = await self.access_token(config['id'])
        if not config.get('model'):
            raise ValidationError('Choose a ChatGPT model in LLM API settings.')
        payload = {'model': config['model'], 'instructions': instructions,
                   'input': [{'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}],
                   'store': False, 'stream': True, 'text': {'format': {'type': 'json_object'}}}
        url = RESOURCE + '/responses'
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                async with session.post(url, json=payload, headers={'Authorization': 'Bearer ' + token},
                                        proxy=proxy_for_url(url), ssl=tls_context(), allow_redirects=False) as response:
                    if response.status != 200:
                        raw = await response.content.read(65536)
                        try:
                            error = json.loads(raw)
                        except ValueError:
                            error = {}
                        raise remote_error(response.status, error)
                    return await read_response(response.content)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise ValidationError('ChatGPT request was interrupted. Retry explicitly; no image was submitted.') from None

    async def close(self):
        for identifier in list(self.attempts):
            await self.cancel(identifier)


async def read_response(content):
    """Bound SSE input and accept only a terminal completed response."""
    buffer, size, lines = b'', 0, []
    async for chunk in content.iter_chunked(16384):
        size += len(chunk)
        if size > 2 * 1024 * 1024:
            raise ValidationError('ChatGPT response is too large.')
        buffer += chunk
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            line = line.rstrip(b'\r')
            if line.startswith(b'data:'):
                lines.append(line[5:].lstrip())
            if line or not lines:
                continue
            raw, lines = b'\n'.join(lines), []
            if raw == b'[DONE]':
                continue
            try:
                event = json.loads(raw)
                kind = event.get('type')
                if kind in ('response.failed', 'response.incomplete', 'error'):
                    raise remote_error(200, event.get('response', event))
                if kind == 'response.completed':
                    response = event['response']
                    if response.get('status') != 'completed':
                        raise ValidationError('ChatGPT did not complete the prompt.')
                    text = ''.join(part['text'] for item in response.get('output', [])
                                   if item.get('type') == 'message' for part in item.get('content', [])
                                   if part.get('type') == 'output_text')
                    return json.loads(text)
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                if isinstance(error, ValidationError):
                    raise
                raise ValidationError('ChatGPT returned invalid prompt data.') from None
    raise ValidationError('ChatGPT stream ended before completion. Retry explicitly.')
