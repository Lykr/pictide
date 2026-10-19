"""Export both vocabulary editions from real, small Parquet input without network."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from scripts import export_vocabularies as exporter


class VocabularyEditionsSmoke(unittest.TestCase):
    def test_two_editions_checksums_reuse_and_default_lock_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset, cache = root / 'datasets', root / 'cache'
            raw = dataset / 'raw/tiny.parquet'
            raw.parent.mkdir(parents=True)
            pq.write_table(pa.table({
                'id': [1, 2, 3],
                'tag_string_general': ['garden flower', 'garden tree', 'flower tree'],
                'rating': ['g', 'q', 'e'],
            }), raw)
            entry = dict(path='tiny.parquet', bytes=raw.stat().st_size,
                         sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
            lock = root / 'resources.json'
            lock.write_text(json.dumps(dict(dataset=dict(
                source='fixture/dataset', revision='fixture-v1', files=[entry]))), encoding='utf-8')
            default_lock = exporter.ROOT / 'corpus/prebuilt.json'
            before = default_lock.read_bytes()
            (root / 'corpus').mkdir()
            profiles = {}
            for edition, excluded in [('filtered', ['questionable', 'explicit']), ('all-ratings', [])]:
                path = root / f'corpus/{edition}.json'
                path.write_text(json.dumps(dict(exclude_posts_with_tags=excluded, exclude_tags=[],
                                                min_tag_occurrences=1, min_cooccurrences=1)), encoding='utf-8')
                profiles[edition] = path

            with (patch.object(exporter, 'ROOT', root), patch('builtins.print'),
                  patch('corpus.download.response', side_effect=AssertionError('unexpected network'))):
                result = exporter.export_vocabularies(dataset, cache, profiles=profiles, lock_path=lock)
                output, manifest = Path(result['output']), result['manifest']
                counts = {}
                for edition, item in manifest['editions'].items():
                    with closing(sqlite3.connect(output / item['file']['path'])) as db:
                        counts[edition] = db.execute('SELECT post_count FROM dataset').fetchone()[0]
                    report = json.loads((output / item['report']['path']).read_text(encoding='utf-8'))
                    self.assertEqual(report['edition'], edition)
                    self.assertEqual(report['file'], item['file'])
                    self.assertEqual(report['fingerprint'], item['fingerprint'])
                self.assertEqual(counts, {'filtered': 1, 'all-ratings': 3})
                self.assertEqual(len(list(output.iterdir())), 6)
                checksums = (output / 'SHA256SUMS').read_text().splitlines()
                self.assertEqual(len(checksums), 5)
                for line in checksums:
                    digest, name = line.split('  ')
                    self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
                for item in manifest['files']:
                    self.assertEqual((output / item['path']).stat().st_size, item['bytes'])
                self.assertEqual(json.loads((output / 'manifest.json').read_text()), manifest)
                self.assertEqual(manifest['release_tag'], 'corpus-editions-' + manifest['fingerprint'])
                self.assertEqual(output.name, 'vocabularies-' + manifest['fingerprint'][:12])
                self.assertEqual(default_lock.read_bytes(), before)
                with patch('corpus.importer.import_parquet', side_effect=AssertionError('cache rebuilt')):
                    self.assertEqual(exporter.export_vocabularies(
                        dataset, cache, profiles=profiles, lock_path=lock), result)
                    (output / 'manifest.json').write_text('broken', encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'different/incomplete'):
                        exporter.export_vocabularies(dataset, cache, profiles=profiles, lock_path=lock)
                self.assertEqual(default_lock.read_bytes(), before)
