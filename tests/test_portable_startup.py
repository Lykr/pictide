"""A few portable startup smokes; native bundling is validated separately."""
from contextlib import closing
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import ANY, patch
import zipfile

from aiohttp import web
from aiohttp.test_utils import TestServer

from backend.application import PictideApplication
from backend.host import open_browser_when_ready
from backend.paths import DataPaths
from corpus.portable import PreparedResources
from scripts.build_portable import build, export_resources
from tests.test_candidate_libraries import vocabulary


class PortableResourcesSmoke(unittest.TestCase):
    def test_build_from_prepared_resources_without_application_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'clean repository'
            front = repo / 'web/dist'
            front.mkdir(parents=True)
            (front / 'index.html').write_text('frontend fixture', encoding='utf-8')
            notices = repo / 'web/src/THIRD_PARTY_NOTICES.md'
            notices.parent.mkdir(parents=True)
            notices.write_text('frontend licenses', encoding='utf-8')
            for name in ('LICENSE', 'NOTICE'):
                (repo / name).write_text('project license fixture', encoding='utf-8')
            library = vocabulary(root / 'neutral.sqlite3')
            snapshot = root / 'model'
            snapshot.mkdir()
            for name in ('model.onnx', 'tokenizer.json', 'config.json', 'tokenizer_config.json', 'special_tokens_map.json'):
                (snapshot / name).write_text('fixture', encoding='utf-8')
            provenance = {'fixture': True, 'dataset_revision': 'pinned-v1'}
            resources = PreparedResources(library, snapshot, provenance)
            dataset, cache, models = (root / name for name in ('datasets', 'cache', 'models'))
            profile = root / 'profile.json'
            output = root / 'release'

            def bundle(command, *, cwd, check):
                self.assertEqual(cwd, repo)
                self.assertTrue(check)
                bundled = Path(command[command.index('--distpath') + 1]) / 'Pictide'
                bundled.mkdir()
                executable = bundled / ('Pictide.exe' if sys.platform == 'win32' else 'Pictide')
                executable.write_text('native fixture', encoding='utf-8')
                for index, arg in enumerate(command[:-1]):
                    if arg == '--add-data':
                        source, destination = command[index + 1].rsplit(os.pathsep, 1)
                        shutil.copytree(source, bundled / '_internal' / destination)

            logger = logging.Logger('portable-build-smoke')
            try:
                with patch('scripts.build_portable.ROOT', repo), \
                        patch('scripts.build_portable.prepare_resources', return_value=resources) as prepare, \
                        patch('scripts.build_portable.subprocess.run', side_effect=bundle), \
                        patch('scripts.build_portable.copy_licenses', side_effect=lambda target: (target / 'Apache-2.0.txt').write_text('license fixture')), \
                        patch('backend.paths.logging.getLogger', return_value=logger), \
                        patch.dict('os.environ'), patch('tempfile.tempdir', tempfile.tempdir), \
                        patch('sys.pycache_prefix', sys.pycache_prefix):
                    result = build(output, dataset_dir=dataset, cache_dir=cache,
                                   models_dir=models, profile=profile)
                    prepare.assert_called_once_with(dataset, cache, profile,
                                                    models_dir=models, prebuilt_library=None, progress=ANY)
            finally:
                for handler in logger.handlers:
                    handler.close()
            self.assertFalse((repo / 'data').exists())
            self.assertEqual(result['resources'], provenance)
            self.assertEqual(json.loads((output / 'build-report.json').read_text())['resources'], provenance)
            with zipfile.ZipFile(result['archive']) as archive:
                seed = 'Pictide/data/runtime/pictide/_internal/resources/'
                manifest = json.loads(archive.read(seed + 'manifest.json'))
                self.assertEqual(manifest['provenance'], provenance)
                self.assertIn(seed + 'libraries/neutral.sqlite3', archive.namelist())
                self.assertFalse(any('/db/' in name or '/images/' in name for name in archive.namelist()))
                exported = root / 'exported.sqlite3'
                exported.write_bytes(archive.read(seed + 'libraries/neutral.sqlite3'))
                with closing(sqlite3.connect(exported)) as db:
                    self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='presets'").fetchone())

    def test_export_initialize_and_preserve_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = vocabulary(root / 'neutral.sqlite3')
            snapshot = root / 'model'
            snapshot.mkdir(parents=True)
            for name in ('model.onnx', 'tokenizer.json', 'config.json', 'tokenizer_config.json', 'special_tokens_map.json'):
                (snapshot / name).write_text('fixture', encoding='utf-8')
            seed = root / 'seed'
            resources = PreparedResources(library, snapshot, {'fixture': True})
            manifest = export_resources(resources, seed)
            self.assertTrue(manifest['files'])
            with closing(sqlite3.connect(seed / 'libraries/neutral.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM tags').fetchone()[0], 2)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='presets'").fetchone())
            target = DataPaths(root / 'portable data')
            PictideApplication.prepare_startup(target, seed)
            model = target.models / 'minilm/config.json'
            self.assertEqual(model.read_text(), 'fixture')
            model.write_text('user-model', encoding='utf-8')
            target.candidate_database.write_bytes(b'personal presets')
            target.database.write_bytes(b'personal history')
            PictideApplication.prepare_startup(target, seed)
            self.assertEqual(model.read_text(), 'user-model')
            self.assertEqual(target.candidate_database.read_bytes(), b'personal presets')
            self.assertEqual(target.database.read_bytes(), b'personal history')

    def test_portable_default_uses_executable_location(self):
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory).resolve() / 'data'
            executable = expected / 'runtime/pictide/Pictide.exe'
            with patch('backend.paths.sys.executable', str(executable)), patch('backend.paths.sys.frozen', True, create=True), patch.dict('os.environ', {}, clear=True):
                self.assertEqual(DataPaths().root, expected)
                self.assertEqual(DataPaths(expected / 'custom').root, expected / 'custom')


class BrowserStartupSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_opens_browser_after_bootstrap_answers(self):
        application = web.Application()
        async def bootstrap(request):
            return web.json_response({'name': 'Pictide'})
        application.router.add_get('/api/bootstrap', bootstrap)
        server = TestServer(application)
        await server.start_server()
        try:
            url = str(server.make_url('/')).rstrip('/')
            with patch('backend.host.webbrowser.open', return_value=True) as browser:
                await open_browser_when_ready(url)
                browser.assert_called_once_with(url)
        finally:
            await server.close()
