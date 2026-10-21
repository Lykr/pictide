"""Guard architectural dependencies and actual realtime transport, not directory names."""
import ast
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer
from backend.host import APPLICATION, create_app
from backend.events import EventHub

from tests import ROOT
def dependencies(path):
    module = '.'.join(path.relative_to(ROOT).with_suffix('').parts)
    package = module.removesuffix('.__init__') if path.name == '__init__.py' else module.rpartition('.')[0]
    result = []
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
        if isinstance(node, ast.Import):
            result.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = '.' * node.level + (node.module or '')
            result.append(importlib.util.resolve_name(name, package) if node.level else name)
    return result


class ArchitectureTests(unittest.TestCase):
    def assert_boundary(self, directory, forbidden):
        for path in (ROOT / directory).rglob('*.py'):
            # Offline data tools are adapters, never imported by online candidate use cases.
            if directory == 'backend/candidate' and path.name in {'importer.py', 'download.py'}:
                continue
            for dependency in dependencies(path):
                self.assertFalse(any(dependency == name or dependency.startswith(name + '.') for name in forbidden),
                                 f'{path.relative_to(ROOT)} imports {dependency}')

    def test_candidate_and_recommendation_are_independent(self):
        self.assert_boundary('backend/candidate', ['aiohttp', 'sqlite3', 'backend.host', 'backend.application',
                                                 'backend.task', 'backend.generation', 'backend.store', 'backend.recommendation'])
        self.assert_boundary('backend/recommendation', ['backend.candidate', 'aiohttp', 'sqlite3', 'backend.host', 'backend.application',
                                                 'backend.task', 'backend.generation', 'backend.store'])

    def test_task_and_store_dependency_directions(self):
        self.assert_boundary('backend/task', ['backend.host', 'backend.application', 'backend.candidate', 'backend.recommendation', 'backend.store.sqlite'])
        self.assert_boundary('backend/generation', ['backend.store', 'backend.task', 'backend.application', 'backend.host'])
        self.assert_boundary('backend/store', ['backend.generation', 'backend.task', 'backend.application', 'backend.host'])
        application = ROOT / 'backend/application.py'
        self.assertFalse(any(name in {'aiohttp', 'sqlite3', 'backend.store.sqlite'} or name.startswith('backend.generation.')
                             for name in dependencies(application)))
        for node in ast.walk(ast.parse(application.read_text(encoding='utf-8'))):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == 'generation':
                self.assertEqual([item.name for item in node.names], ['backend_capabilities'])

    def test_frontend_has_one_mount_and_no_backend_imports(self):
        mounts = []
        for path in (ROOT / 'web/src').rglob('*'):
            if path.suffix not in {'.ts', '.tsx', '.js', '.mjs'}:
                continue
            source = path.read_text(encoding='utf-8')
            if 'createRoot(' in source:
                mounts.append(path.relative_to(ROOT).as_posix())
            self.assertNotIn('/backend/', source)
            self.assertNotIn('pictide_web', source)
        self.assertEqual(mounts, ['web/src/main.tsx'])
        shell = (ROOT / 'web/src/feed.tsx').read_text(encoding='utf-8')
        self.assertIn('data-view="prompts"', shell)
        self.assertNotIn('target="_blank"', shell)


class RealtimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_notifications_are_bounded_and_shutdown_releases_subscribers(self):
        hub = EventHub()
        stream = hub.stream()
        first = await anext(stream)
        self.assertEqual(first['topic'], 'ready')
        for index in range(200):
            hub.publish(str(index))
        latest = await anext(stream)
        self.assertEqual(latest['topic'], '199')
        self.assertEqual(latest['revision'], 200)
        hub.close()
        with self.assertRaises(StopAsyncIteration):
            await anext(stream)
        self.assertFalse(hub.subscribers)

    async def test_sse_delivers_committed_application_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(directory)
            client = TestClient(TestServer(app))
            await client.start_server()
            response = None
            try:
                response = await client.get('/api/events')
                self.assertEqual(response.status, 200)
                self.assertIn('text/event-stream', response.headers['Content-Type'])
                async def next_data():
                    while True:
                        line = await asyncio.wait_for(response.content.readline(), timeout=3)
                        if line.startswith(b'data: '):
                            return json.loads(line[6:])
                initial = await next_data()
                result = await client.put('/api/settings/history', json={'unliked_retention_days': 0})
                self.assertEqual(result.status, 200)
                event = await next_data()
                self.assertEqual(event['topic'], 'settings')
                self.assertGreater(event['revision'], initial['revision'])
                self.assertEqual(app[APPLICATION].history.get()['unliked_retention_days'], 0)
            finally:
                if response:
                    response.close()
                await client.close()
