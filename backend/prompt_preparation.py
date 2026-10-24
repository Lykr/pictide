"""Application-owned preparation coordination; no candidate or ranking algorithms."""
import asyncio
import hashlib
import json

from .domain import ConflictError, ValidationError
from .generation import backend_capabilities
from .prompting import PromptRenderer


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


class PromptPreparation:
    def __init__(self, store):
        self.store = store
        self.renderer = PromptRenderer()
        # One conversion per application at a time, shared by previews and generation.
        self.lock = asyncio.Lock()

    async def prepare(self, identifier, backend, candidate, *, mode='random', previous=None, preview_id=None, automatic=False):
        settings = await asyncio.to_thread(self.store.settings)
        signature = fingerprint({'backend': backend, 'llm_revision': settings['revision']})
        semantic = {key: candidate[key] for key in ('positive', 'negative')}
        if preview_id:
            if not isinstance(preview_id, str) or len(preview_id) > 160:
                raise ValidationError('Invalid prompt preparation identifier.')
            record = await asyncio.to_thread(self.store.get, preview_id)
            if not record or not record['result'] or record['document']['signature'] != signature or record['document']['candidate'] != semantic:
                raise ConflictError('Prompt preview is out of date. Prepare a new preview.')
            return record['result']
        if previous and previous.get('rendered', {}).get('signature') == signature:
            if all(previous.get(k) == semantic[k] for k in semantic) and mode in ('along', 'stay'):
                return previous['rendered']
        else:
            previous = None
        document = {'signature': signature, 'candidate': semantic, 'mode': mode,
                    'previous': previous if mode == 'along' else None}
        async with self.lock:
            record = await asyncio.to_thread(self.store.reserve, identifier, fingerprint(document), document)
            if record['result']:
                return record['result']
            if automatic and record['attempted']:
                raise ValidationError('An interrupted LLM request has no saved result. Save Roam settings to retry.')
            if not settings['revision']:
                raise ValidationError('Configure the prompt LLM API before generating natural-language prompts.')
            reference = ({'tags': {k: previous[k] for k in semantic},
                          'prompt': {k: previous['rendered'][k] for k in semantic}} if previous and mode == 'along' else None)
            await asyncio.to_thread(self.store.started, identifier)
            text = await self.renderer.render(settings, semantic, mode=mode, previous=reference,
                                             negative_channel=backend_capabilities(backend)['negative_prompt'])
            current = await asyncio.to_thread(self.store.settings)
            if current['revision'] != settings['revision']:
                raise ConflictError('LLM settings changed during prompt preparation. Retry with the new settings.')
            result = dict(text, preparation_id=identifier, signature=signature, prompt_type='natural_language')
            await asyncio.to_thread(self.store.finish, identifier, result)
            return result
