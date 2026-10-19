"""Portable resource preparation with a tiny pinned dataset, without network."""
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import pyarrow as pa
import pyarrow.parquet as pq

from corpus.portable import prepare_resources
from scripts.prepare_vocabulary import export_vocabulary


class Response(io.BytesIO):
    status = 200
    headers = {}


class PortableCacheSmoke(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.dataset = self.root / 'datasets/danbooru'
        self.cache = self.root / 'cache/portable'
        self.profile = self.root / 'profile.json'
        self.profile.write_text(json.dumps({
            'exclude_tags': ['questionable', 'explicit'],
            'min_tag_occurrences': 1, 'min_cooccurrences': 1,
        }), encoding='utf-8')
        parquet = self.root / 'tiny.parquet'
        pq.write_table(pa.table({
            'id': [1, 2, 3],
            'tag_string_general': ['garden flower', 'garden tree', 'flower tree'],
            'rating': ['g', 'q', 'e'],
        }), parquet)
        self.files = {'tiny.parquet': parquet.read_bytes()}

        def entry(name):
            payload = self.files[name]
            return {'path': name, 'bytes': len(payload),
                    'sha256': hashlib.sha256(payload).hexdigest()}

        self.lock = self.root / 'resources.lock.json'
        self.lock.write_text(json.dumps({
            'dataset': {'source': 'fixture/dataset', 'revision': 'dataset-v1',
                        'files': [entry('tiny.parquet')]},
        }), encoding='utf-8')
        self.downloads = []

    def response(self, url, headers=None):
        name = Path(unquote(urlsplit(url).path)).name
        self.downloads.append(name)
        return Response(self.files[name])

    def prepare(self):
        return prepare_resources(self.dataset, self.cache, self.profile,
                                 lock_path=self.lock,
                                 progress=lambda _: None)

    def test_cold_build_and_offline_hit_ignore_json_formatting(self):
        with patch('corpus.download.response', side_effect=self.response):
            prepared = self.prepare()
        self.assertCountEqual(self.downloads, self.files)
        self.assertEqual(prepared.library.name, 'vocabulary.sqlite3')
        self.assertTrue((prepared.library.parent / 'state.sqlite3').is_file())
        self.assertTrue((prepared.library.parent / 'report.json').is_file())
        self.assertTrue((self.dataset / 'download.sqlite3').is_file())
        self.assertTrue((self.dataset / 'raw/tiny.parquet').is_file())
        self.assertEqual(set(prepared.provenance), {'library'})
        self.assertFalse(any(self.root.rglob('model.onnx')))
        with closing(sqlite3.connect(prepared.library)) as db:
            tags = {row[0] for row in db.execute('SELECT name FROM tags')}
            self.assertEqual(tags, {'garden', 'flower', 'tree', 'general'})
            self.assertEqual(db.execute('SELECT post_count FROM dataset').fetchone()[0], 3)
        self.profile.write_text('''{
  "min_cooccurrences": 1, "min_tag_occurrences": 1,
  "exclude_tags": ["explicit", "questionable", "explicit"]
}\n''', encoding='utf-8')
        shutil.rmtree(self.dataset)
        with patch('corpus.download.response', side_effect=AssertionError('warm cache used network')):
            cached = self.prepare()
        self.assertEqual(cached.library, prepared.library)
        self.assertEqual(cached.provenance, prepared.provenance)

    def test_config_changes_reuse_dataset_and_damaged_outputs_are_repaired(self):
        with patch('corpus.download.response', side_effect=self.response):
            original = self.prepare()
        raw = self.dataset / 'raw/tiny.parquet'
        identity = (raw.read_bytes(), raw.stat().st_mtime_ns)
        options = json.loads(self.profile.read_text())
        options['min_cooccurrences'] = 2
        self.profile.write_text(json.dumps(options), encoding='utf-8')
        with patch('corpus.download.response', side_effect=AssertionError('raw data downloaded again')):
            changed = self.prepare()
        self.assertNotEqual(changed.library, original.library)
        self.assertEqual((raw.read_bytes(), raw.stat().st_mtime_ns), identity)
        self.assertTrue(original.library.is_file())
        changed.library.write_bytes(b'corrupted cached vocabulary')
        self.downloads.clear()
        with patch('corpus.download.response', side_effect=self.response):
            repaired = self.prepare()
        self.assertEqual(self.downloads, [])
        self.assertEqual(repaired.library, changed.library)
        with closing(sqlite3.connect(repaired.library)) as db:
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT count(*) FROM correlations').fetchone()[0], 0)
        self.assertEqual((raw.read_bytes(), raw.stat().st_mtime_ns), identity)
        shutil.rmtree(self.cache)
        with patch('corpus.download.response', side_effect=AssertionError('cache reset downloaded source or model')):
            rebuilt = self.prepare()
        self.assertTrue(rebuilt.library.is_file())
        self.assertEqual((raw.read_bytes(), raw.stat().st_mtime_ns), identity)

    def test_existing_dataset_revision_conflict_preserves_original_files(self):
        with patch('corpus.download.response', side_effect=self.response):
            self.prepare()
        raw = self.dataset / 'raw/tiny.parquet'
        identity = (raw.read_bytes(), raw.stat().st_mtime_ns)
        manifest = self.dataset / 'download.sqlite3'
        with closing(sqlite3.connect(manifest)) as db, db:
            db.execute("UPDATE files SET revision='another-dataset-version'")
        manifest_before = manifest.read_bytes()
        options = json.loads(self.profile.read_text())
        options['min_cooccurrences'] = 2
        self.profile.write_text(json.dumps(options), encoding='utf-8')
        with patch('corpus.download.response', side_effect=AssertionError('conflicting dataset downloaded')):
            with self.assertRaises((ValueError, RuntimeError)):
                self.prepare()
        self.assertEqual(manifest.read_bytes(), manifest_before)
        self.assertEqual((raw.read_bytes(), raw.stat().st_mtime_ns), identity)

    def test_prebuilt_consumption_without_processing_dependencies_or_raw_data(self):
        output = self.root / 'export'
        resource_lock = self.root / 'prebuilt.json'
        with patch('corpus.download.response', side_effect=self.response), patch('builtins.print'):
            export_vocabulary(self.dataset, self.cache, self.profile, output_dir=output,
                              resource_lock=resource_lock, lock_path=self.lock)
        shutil.rmtree(self.dataset)
        shutil.rmtree(self.cache)
        self.downloads.clear()
        with (patch('corpus.portable.version', side_effect=AssertionError('processing dependency inspected')),
              patch('corpus.importer.import_parquet', side_effect=AssertionError('raw processing started')),
              patch('corpus.download.response', side_effect=self.response)):
            prepared = prepare_resources(self.dataset, self.cache, self.profile,
                                         lock_path=self.lock, prebuilt_library=output,
                                         prebuilt_lock_path=resource_lock, progress=lambda _: None)
        self.assertEqual(prepared.library, output / 'vocabulary.sqlite3')
        self.assertEqual(self.downloads, [])
        self.assertFalse(self.dataset.exists())
        self.assertFalse(self.cache.exists())

    def test_prebuilt_rejects_stale_profile_and_corrupt_files_without_fallback(self):
        output, resource_lock = self.root / 'export', self.root / 'prebuilt.json'
        with patch('corpus.download.response', side_effect=self.response), patch('builtins.print'):
            export_vocabulary(self.dataset, self.cache, self.profile, output_dir=output,
                              resource_lock=resource_lock, lock_path=self.lock)
        def consume():
            return prepare_resources(self.dataset, self.cache, self.profile,
                                     lock_path=self.lock, prebuilt_library=output,
                                     prebuilt_lock_path=resource_lock, progress=lambda _: None)
        original = self.profile.read_text()
        options = json.loads(original)
        options['min_tag_occurrences'] = 2
        self.profile.write_text(json.dumps(options))
        with patch('corpus.portable.prepare_vocabulary', side_effect=AssertionError('fallback rebuild')):
            with self.assertRaisesRegex(ValueError, 'stale'):
                consume()
            self.profile.write_text(original)
            (output / 'vocabulary.sqlite3').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'failed verification'):
                consume()
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true'}):
            with self.assertRaisesRegex(ValueError, '--prebuilt-library'):
                self.prepare()
