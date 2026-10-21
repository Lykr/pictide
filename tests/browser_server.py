"""Disposable HTTP fixture for browser smokes; never prepares models or uses a GPU."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiohttp import web
from backend import host
from backend.host import APPLICATION
from backend.recommendation.service import RecommendationService
from tests.backend.application.test_app import FakeBackend, configuration
from tests.backend.candidate.test_candidate_libraries import vocabulary
from tests.backend.recommendation.test_recommendation_application import CPUEncoder


class BrowserBackend(FakeBackend):
    async def inspect(self, prompt_id):
        result = await super().inspect(prompt_id)
        result['outputs'] = result['outputs'][:1]
        return result


async def main():
    workspace = ROOT / 'dev/verification/browser'
    workspace.mkdir(parents=True, exist_ok=True)
    host.STATIC = workspace / 'dist'
    if not (host.STATIC / 'index.html').is_file():
        raise RuntimeError('Build the isolated browser frontend first; see docs/dev/testing.md')
    with tempfile.TemporaryDirectory(prefix='data-', dir=workspace) as temporary:
        data = Path(temporary)
        vocabulary(data / 'libraries/neutral.sqlite3')
        backend = BrowserBackend()
        app = host.create_app(data, lambda config, session: backend)
        application = app[APPLICATION]
        application.recommendation = RecommendationService(application.recommendation_store, CPUEncoder())
        application.storage.save_backend({**configuration(), 'id': 'fixture', 'name': 'Browser fixture'})
        preset = application.candidates.save_preset({'name': 'Browser fixture', 'document': {
            'base_positive': [], 'base_negative': [], 'min_tags': 2, 'max_tags': 2,
            'pmi_threshold': 0, 'min_cooccurrence': 10, 'change_budget': 1,
        }})
        application.roam.save(0, 'fixture', preset['id'])
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            site = web.TCPSite(runner, '127.0.0.1', 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
            print(json.dumps({'url': f'http://127.0.0.1:{port}', 'dataDirectory': str(data)}), flush=True)
            # Closing the owner's pipe releases both the service and temporary data.
            await asyncio.to_thread(sys.stdin.buffer.read)
        finally:
            await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
