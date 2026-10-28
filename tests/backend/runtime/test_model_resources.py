"""Small model download and startup-gate smokes, with no public network."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import host
from backend.paths import DataPaths
from backend.recommendation.resources import prepare_model


class Response(io.BytesIO):
    def __init__(self, payload, *, offset=0, total=None):
        super().__init__(payload)
        self.status = 206 if offset else 200
        self.headers = {'Content-Range': f'bytes {offset}-{total - 1}/{total}'} if offset else {}


class ModelPreparationSmoke(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.model = self.root / 'models/minilm'
        self.model.mkdir(parents=True)
        self.payload = b'a small pinned model fixture'
        self.catalog = dict(source='fixture/model', revision='fixed-revision', files=[dict(
            path='model.onnx', bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest())])

    def test_resume_then_offline_reuse(self):
        (self.model / 'model.onnx.part').write_bytes(self.payload[:8])

        def response(request, *, timeout):
            self.assertEqual(request.get_header('Range'), 'bytes=8-')
            self.assertIn('/fixed-revision/model.onnx', request.full_url)
            return Response(self.payload[8:], offset=8, total=len(self.payload))

        with patch('backend.recommendation.resources.urlopen', side_effect=response):
            prepare_model(self.model, catalog=self.catalog, progress=lambda _: None)
        self.assertEqual((self.model / 'model.onnx').read_bytes(), self.payload)
        self.assertFalse((self.model / 'model.onnx.part').exists())
        with patch('backend.recommendation.resources.urlopen', side_effect=AssertionError('offline reuse made a request')):
            prepare_model(self.model, catalog=self.catalog, progress=lambda _: None)

    def test_replacement_preserves_existing_file_and_requires_correct_hash(self):
        target = self.model / 'model.onnx'
        target.write_bytes(b'previous model')
        with (patch('backend.recommendation.resources.urlopen', side_effect=lambda *a, **k: Response(b'x' * len(self.payload))),
              patch('backend.recommendation.resources.time.sleep')):
            with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                prepare_model(self.model, catalog=self.catalog, progress=lambda _: None)
        self.assertEqual(target.read_bytes(), b'previous model')
        self.assertTrue((self.model / 'model.onnx.part').exists())
        with patch('backend.recommendation.resources.urlopen', side_effect=lambda *a, **k: Response(self.payload)):
            prepare_model(self.model, catalog=self.catalog, progress=lambda _: None)
        self.assertEqual(target.read_bytes(), self.payload)
        backups = list(self.model.glob('model.onnx.before-download-*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'previous model')

    def test_failed_download_stops_before_service_and_browser_start(self):
        (self.model / 'model.onnx.part').write_bytes(self.payload[:8])
        history = self.root / 'db/pictide.sqlite3'
        history.parent.mkdir()
        history.write_bytes(b'personal history fixture')
        paths = DataPaths(self.root).ensure()
        with (patch('backend.paths.DataPaths.configure_runtime', return_value=paths),
              patch('backend.setup.vocabulary.prepare_vocabulary'),
              patch('backend.recommendation.resources.model_catalog', return_value=self.catalog),
              patch('backend.recommendation.resources.urlopen', side_effect=OSError('connection unavailable')),
              patch('backend.recommendation.resources.time.sleep'),
              patch('backend.host.create_app') as create,
              patch('backend.host.web.run_app') as listen,
              patch('backend.host.webbrowser.open') as browser):
            with self.assertRaises(SystemExit) as result:
                host.main(['--data-dir', str(self.root)])
        self.assertEqual(result.exception.code, 1)
        create.assert_not_called()
        listen.assert_not_called()
        browser.assert_not_called()
        self.assertEqual((self.model / 'model.onnx.part').read_bytes(), self.payload[:8])
        self.assertEqual(history.read_bytes(), b'personal history fixture')
