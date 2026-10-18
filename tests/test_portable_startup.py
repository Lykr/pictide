"""A few portable startup smokes; native bundling is validated separately."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer

from backend.application import PictideApplication
from backend.host import open_browser_when_ready
from backend.paths import DataPaths
from scripts.build_portable import export_resources
from tests.test_candidate_libraries import vocabulary


class PortableResourcesSmoke(unittest.TestCase):
    def test_export_initialize_and_preserve_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = DataPaths(root / 'source').ensure()
            vocabulary(source.libraries / 'neutral.sqlite3')
            with closing(sqlite3.connect(source.candidate_database)) as db, db:
                db.execute('CREATE TABLE library_selection(id INTEGER PRIMARY KEY,filename TEXT)')
                db.execute("INSERT INTO library_selection VALUES(1,'neutral.sqlite3')")
            repository = source.cache / 'embeddings/models--Qdrant--all-MiniLM-L6-v2-onnx'
            snapshot = repository / 'snapshots/abc123'
            snapshot.mkdir(parents=True)
            for name in ('model.onnx', 'tokenizer.json', 'config.json', 'tokenizer_config.json', 'special_tokens_map.json'):
                (snapshot / name).write_text('fixture', encoding='utf-8')
            (repository / 'refs').mkdir()
            (repository / 'refs/main').write_text('abc123', encoding='utf-8')
            seed = root / 'seed'
            export_resources(source, seed)
            with closing(sqlite3.connect(seed / 'libraries/neutral.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM tags').fetchone()[0], 2)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='presets'").fetchone())
            target = DataPaths(root / 'portable data')
            PictideApplication.prepare_startup(target, seed)
            model = target.cache / 'embeddings/models--Qdrant--all-MiniLM-L6-v2-onnx/refs/main'
            self.assertEqual(model.read_text(), 'abc123')
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
