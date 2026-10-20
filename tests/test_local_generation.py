"""Local HTTP/resource and installation smokes without large downloads or GPU work."""
from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from backend import local_generation as local
from backend.paths import DataPaths


class LocalGenerationSmoke(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.payload = b'pinned model fixture with enough data for several ranges'
        payload = self.payload
        self.ranges = ranges = []
        self.queries = queries = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                start, end = map(int, self.headers['Range'].removeprefix('bytes=').split('-'))
                ranges.append((start, end))
                queries.append(parse_qs(urlsplit(self.path).query))
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{len(payload)}')
                self.end_headers()
                self.wfile.write(payload[start:end + 1])

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.resource = local.Resource('diffusion_models/model.bin',
                                       f'http://127.0.0.1:{server.server_port}/model?download=true', len(payload),
                                       hashlib.sha256(payload).hexdigest())

    def test_range_resume_atomic_completion_and_offline_reuse(self):
        destination = self.root / 'model.bin'
        destination.with_name('model.bin.part').write_bytes(self.payload[:7])
        progress = []
        with patch.object(local, '_RANGE_BYTES', 11):
            local.download_resource(self.resource, destination, progress.append)
        self.assertEqual(self.ranges[0], (7, 17))
        self.assertEqual(self.queries[0], {'download': ['true'], 'pictide_part': ['7']})
        self.assertEqual(self.queries[1]['pictide_part'], ['18'])
        self.assertGreater(len(self.ranges), 2)
        self.assertEqual(destination.read_bytes(), self.payload)
        self.assertFalse(destination.with_name('model.bin.part').exists())
        with patch.object(local, 'urlopen', side_effect=AssertionError('must be offline')):
            local.download_resource(self.resource, destination)
        self.assertEqual(progress[-1]['phase'], 'verify')

    def test_cancel_leaves_partial_and_bad_hash_never_publishes(self):
        destination = self.root / 'model.bin'

        def cancel(event):
            if event['phase'] == 'download':
                raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            local.download_resource(self.resource, destination, cancel)
        self.assertFalse(destination.exists())
        self.assertTrue(destination.with_name('model.bin.part').exists())
        bad = replace(self.resource, sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            local.download_resource(bad, destination)
        self.assertFalse(destination.exists())
        destination.write_bytes(b'user-owned model')
        with self.assertRaises(FileExistsError):
            local.download_resource(self.resource, destination)
        self.assertEqual(destination.read_bytes(), b'user-owned model')

    def test_complete_recipe_validates_and_catalog_rejects_missing_workflow(self):
        config = local.model_connection('anima-turbo-v1-1', 'http://127.0.0.1:8190')
        self.assertEqual(config['workflow_mode'], 'custom')
        self.assertEqual(config['workflow']['28']['inputs'], dict(width=832, height=1248, batch_size=1))
        sampler = config['workflow']['19']['inputs']
        self.assertEqual((sampler['steps'], sampler['cfg'], sampler['sampler_name'], sampler['scheduler']),
                         (10, 1, 'euler', 'simple'))
        self.assertEqual(config['bindings']['positive'], {'node_id': '11', 'input': 'text'})
        self.assertEqual(config['output_nodes'], ['1'])
        self.assertTrue(local.recipe_catalog()['anima-turbo-v1-1']['noncommercial'])
        invalid = replace(local.RECIPES['anima-turbo-v1-1'], workflow_file='')
        with patch.object(local, 'RECIPES', {'incomplete': invalid}):
            with self.assertRaisesRegex(ValueError, 'Incomplete model recipe'):
                local.recipe_catalog()
        self.assertTrue(all(len(item.sha256) == 64 for _, item in local.PROFILES.values()))
        self.assertEqual(len(local.EXTRACTOR.sha256), 64)

    def test_runtime_staged_then_reused_and_models_not_overwritten(self):
        paths = DataPaths(self.root / 'data').ensure()
        extracted = []

        def extract(archive, extractor, staging, progress):
            package = staging / 'ComfyUI_windows_portable'
            (package / 'python_embeded').mkdir(parents=True)
            (package / 'ComfyUI').mkdir()
            (package / 'python_embeded/python.exe').touch()
            (package / 'ComfyUI/main.py').touch()
            extracted.append(package)

        recipe = replace(local.RECIPES['anima-turbo-v1-1'], files=(self.resource,))
        with patch.object(local, 'PROFILES', {'fixture': ('Fixture', self.resource)}), \
                patch.object(local, 'EXTRACTOR', self.resource), \
                patch.object(local, 'RECIPES', {'fixture': recipe}), \
                patch.object(local, '_extract', side_effect=extract):
            result = local.prepare_local_comfy(paths, 'fixture', 'fixture')
            self.assertEqual(result['mode'], 'managed')
            self.assertEqual(len(extracted), 1)
            self.assertTrue((paths.runtime / 'comfyui/pictide-install.json').is_file())
            model = paths.models / 'generation' / self.resource.path
            self.assertEqual(model.read_bytes(), self.payload)
            with patch.object(local, 'urlopen', side_effect=AssertionError('must reuse')):
                local.prepare_local_comfy(paths, 'fixture', 'fixture')
            self.assertEqual(len(extracted), 1)
            model.write_bytes(b'user replacement')
            with self.assertRaises(FileExistsError):
                local.prepare_local_comfy(paths, 'fixture', 'fixture')
            self.assertEqual(model.read_bytes(), b'user replacement')


if __name__ == '__main__':
    unittest.main()
