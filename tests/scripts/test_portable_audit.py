"""Prevent environment mixing and unreviewed portable-package bloat."""
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.portable_audit import audit_builder, audit_package
from scripts.build_portable import copy_licenses
from scripts.smoke_portable import smoke_inference
from backend.paths import DataPaths
from backend.store.sqlite import Repository


class PortableAuditTests(unittest.TestCase):
    def test_license_directories_do_not_copy_python_tools_or_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            distributions = {}
            for name in ('aiohttp', 'fastembed', 'numpy', 'PyJWT', 'cryptography', 'packaging', 'pyinstaller', 'truststore'):
                sources = {'LICENSE': b'neutral license terms'}
                if name == 'packaging':
                    sources = {'licenses/LICENSE.APACHE': b'Apache license fixture',
                               'licenses/__init__.py': b'unused source',
                               'licenses/__pycache__/_spdx.pyc': b'unused bytecode'}
                for path, content in sources.items():
                    target = root / name / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                distributions[name] = SimpleNamespace(metadata={'Name': name}, version='1.0',
                    requires=['packaging'] if name == 'fastembed' else [],
                    files=[Path(path) for path in sources],
                    locate_file=lambda path, base=root / name: base / path)
            target = root / 'result'
            with patch('scripts.build_portable.metadata.distribution', side_effect=distributions.__getitem__):
                copy_licenses(target)
            self.assertEqual((target / 'packaging/LICENSE.APACHE').read_bytes(), b'Apache license fixture')
            self.assertEqual((target / 'Apache-2.0.txt').read_bytes(), b'neutral license terms')
            self.assertFalse(list(target.rglob('*.py')) + list(target.rglob('*.pyc')))

    def test_external_python_dependencies_are_rejected_before_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / 'builder/site-packages'
            foreign = root / 'other/site-packages'
            distribution = SimpleNamespace(metadata={'Name': 'numpy'}, version='1.0',
                                           locate_file=lambda _: foreign)
            with patch('scripts.portable_audit.sysconfig.get_path', return_value=str(native)), \
                    patch('scripts.portable_audit.metadata.distributions', return_value=[distribution]), \
                    patch('scripts.portable_audit.importlib.util.find_spec',
                          return_value=SimpleNamespace(origin=str(native / 'package/__init__.py'))):
                with self.assertRaisesRegex(RuntimeError, 'remove borrowed PYTHONPATH'):
                    audit_builder()

    def test_shadowed_modules_are_rejected_even_with_native_distribution_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / 'builder/site-packages'
            foreign = Path(directory) / 'borrowed/numpy/__init__.py'
            with patch('scripts.portable_audit.sysconfig.get_path', return_value=str(native)), \
                    patch('scripts.portable_audit.metadata.distributions', return_value=[]), \
                    patch('scripts.portable_audit.importlib.util.find_spec',
                          return_value=SimpleNamespace(origin=str(foreign))):
                with self.assertRaisesRegex(RuntimeError, 'must be installed into this interpreter'):
                    audit_builder()

    def test_duplicate_runtime_and_accidental_sources_or_resources_fail_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, contents in {'_internal/blas.dll': b'neutral DLL',
                                   '_internal/numpy.libs/blas.dll': b'neutral DLL',
                                   '_internal/onnxruntime/tool.py': b'unused tool source',
                                   '_internal/resources/words.sqlite3': b'vocabulary fixture',
                                   '_internal/model.onnx': b'model fixture'}.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
            result = audit_package(root)
            self.assertEqual(result['file_count'], 5)
            self.assertEqual(len(result['violations']), 4)
            self.assertTrue(any('Duplicate binary' in issue for issue in result['violations']))
            self.assertEqual(len(result['duplicate_contents']), 1)
            self.assertEqual(result['unpacked_bytes'], sum(row['bytes'] for row in result['files']))

    def test_notices_binary_aliases_and_different_versions_are_reported_without_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = {'licenses/a/LICENSE': b'shared attribution', 'licenses/b/LICENSE': b'shared attribution',
                      '_internal/alias.so': b'library', '_internal/real.so': b'library',
                      '_internal/a/blas.dll': b'one version', '_internal/b/blas.dll': b'another version'}
            for name, contents in inputs.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
            result = audit_package(root)
            self.assertEqual(result['violations'], [])
            self.assertEqual(len(result['duplicate_contents']), 2)
            self.assertEqual({row['path'] for row in result['files']}, set(inputs))
            for name, contents in inputs.items():
                self.assertEqual((root / name).read_bytes(), contents)


class NativeInferenceSmokeTests(unittest.TestCase):
    def test_score_requires_new_embeddings_and_never_exposes_a_queued_job(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'data'
            database = DataPaths(data).database
            storage = Repository(database)

            def score(path, *, timeout):
                self.assertTrue(path.endswith('/preference-score'))
                self.assertEqual(timeout, 60)
                self.assertEqual(storage.backends(), [])
                with storage.connection() as db:
                    self.assertEqual(db.execute('SELECT status FROM jobs').fetchall()[0][0], 'completed')
                    self.assertEqual(db.execute('SELECT count(*) FROM recommendation_vectors').fetchone()[0], 0)
                    vector = struct.pack('<384f', 1., *([0.] * 383))
                    db.executemany('INSERT INTO recommendation_vectors VALUES (?,?,?)',
                                   [('fixture', text, vector) for text in ('garden', 'blue sky')])
                return {'status': 'scored', 'score': 0.}

            self.assertEqual(smoke_inference(data, score)['dimension'], 384)

    def test_success_status_without_inference_does_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'data'
            Repository(DataPaths(data).database)
            with self.assertRaisesRegex(RuntimeError, 'did not persist the expected embeddings'):
                smoke_inference(data, lambda *args, **kwargs: {'status': 'scored', 'score': 0.})


if __name__ == '__main__':
    unittest.main()
