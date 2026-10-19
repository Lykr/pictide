import math
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
import tempfile
from pathlib import Path
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from corpus.importer import import_parquet


class ImportSmoke(unittest.TestCase):
    def make_files(self, root):
        rows = []
        for index in range(500):
            tags = []
            if index < 200:
                tags += ['black_hair', 'black_hair']
            if 190 <= index < 390:
                tags += ['standing']
            if index < 100:
                tags += ['exact_100']
            if index < 99:
                tags += ['only_99']
            if 191 <= index < 200 or 390 <= index < 481:
                tags += ['nine_overlap']
            if index % 5 == 0:
                tags += ['every_fifth']
            rows.append((index, ' '.join(tags), ('g', 's', 'q')[index] if index < 3 else 'e'))
        paths = []
        for number, chunk in enumerate((rows[:250] + [(0, 'discarded_duplicate', 'invalid')],
                                        [(249, 'discarded_cross_shard', 'invalid')] + rows[250:])):
            path = root / f'{number}.parquet'
            pq.write_table(pa.table({
                'id': [row[0] for row in chunk],
                'tag_string_general': [row[1] for row in chunk],
                'rating': [row[2] for row in chunk],
                'tag_string_character': ['character_only'] * len(chunk),
                'tag_string_artist': ['artist_only'] * len(chunk),
                'tag_string_copyright': ['copyright_only'] * len(chunk),
                'tag_string_meta': ['meta_only'] * len(chunk),
            }), path, row_group_size=195)
            paths.append(path)
        return paths

    def inspect(self, path):
        with closing(sqlite3.connect(path)) as db:
            tags = db.execute('SELECT name,post_count FROM tags ORDER BY name').fetchall()
            pairs = db.execute('SELECT a.name,b.name,c.pmi,c.count FROM correlations c JOIN tags a ON a.id=c.tag_a JOIN tags b ON b.id=c.tag_b ORDER BY a.name,b.name').fetchall()
            return tags, pairs, db.execute('SELECT post_count,status FROM dataset').fetchone()

    def test_general_frequency_filter_pmi_and_deduplication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); files = self.make_files(root); target = root / 'candidate.sqlite3'
            result = import_parquet(files, target, block_size=2, progress=lambda _: None)
            self.assertEqual(result['post_count'], 500)
            self.assertEqual(result['min_cooccurrence'], 10)
            tags, pairs, status = self.inspect(target)
            self.assertEqual(tags, [('black_hair', 200), ('every_fifth', 100), ('exact_100', 100), ('explicit', 497), ('general', 1), ('nine_overlap', 100), ('questionable', 1), ('sensitive', 1), ('standing', 200)])
            self.assertEqual(status, (500, 'ready'))
            counts = dict(tags)
            for a, b, pmi, count in pairs:
                self.assertAlmostEqual(pmi, math.log2(count * 500 / (counts[a] * counts[b])))
            # Five co-occurrences in each of two row groups must survive globally.
            self.assertIn(('black_hair', 'standing', -3.0, 10), pairs)
            self.assertIn(('every_fifth', 'exact_100', 0.0, 20), pairs)
            self.assertTrue(all(count >= 10 for _, _, _, count in pairs))
            self.assertNotIn(('nine_overlap', 'standing'), {(a, b) for a, b, _, _ in pairs})
            self.assertNotIn(('black_hair', 'nine_overlap'), {(a, b) for a, b, _, _ in pairs})
            with closing(sqlite3.connect(target.with_name('candidate-state.sqlite3'))) as state:
                ids = {name: index + 1 for index, (name, _) in enumerate(tags)}
                self.assertEqual(state.execute('SELECT count FROM pair_counts WHERE tag_a=? AND tag_b=?', (ids['nine_overlap'], ids['standing'])).fetchone()[0], 9)
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual([row[1] for row in db.execute('PRAGMA table_info(tags)')], ['id', 'name', 'post_count'])
                self.assertEqual({row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}, {'tags', 'correlations', 'dataset'})
            self.assertTrue(target.with_name('candidate-state.sqlite3').exists())

    def test_resume_does_not_double_count_committed_pair_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); files = self.make_files(root); target = root / 'resumed.sqlite3'
            def interrupt(message):
                if 'pair block' in message:
                    raise RuntimeError('simulated interruption')
            with self.assertRaises(RuntimeError):
                import_parquet(files, target, block_size=2, progress=interrupt)
            import_parquet(files, target, block_size=2, progress=lambda _: None)
            fresh = root / 'fresh.sqlite3'
            import_parquet(files, fresh, block_size=2, progress=lambda _: None)
            self.assertEqual(self.inspect(target), self.inspect(fresh))

    def test_filters_preserve_posts_ratings_and_original_pmi(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); files = self.make_files(root); target = root / 'filtered.sqlite3'
            result = import_parquet(files, target, min_tag_occurrences=200,
                min_cooccurrences=1, exclude_tags=['standing', 'general'], progress=lambda _: None)
            tags, pairs, status = self.inspect(target)
            self.assertEqual(tags, [('black_hair', 200), ('explicit', 497), ('questionable', 1), ('sensitive', 1)])
            self.assertEqual(status, (500, 'ready'))
            self.assertEqual(result['min_cooccurrence'], 1)
            self.assertIn(('black_hair', 'sensitive', math.log2(2.5), 1), pairs)
            counts = dict(tags)
            for a, b, pmi, count in pairs:
                self.assertAlmostEqual(pmi, math.log2(count * 500 / (counts[a] * counts[b])))

    def test_pair_threshold_can_reuse_completed_counts_but_tag_filters_cannot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); files = self.make_files(root); state = root / 'counts.sqlite3'
            base = root / 'base.sqlite3'; compact = root / 'compact.sqlite3'
            import_parquet(files, base, state_path=state, progress=lambda _: None)
            messages = []
            result = import_parquet(files, compact, state_path=state, min_cooccurrences=20, progress=messages.append)
            self.assertEqual(result['min_cooccurrence'], 20)
            self.assertFalse(any('pair block' in message or 'Frequency pass' in message for message in messages))
            base_tags, base_pairs, _ = self.inspect(base)
            compact_tags, compact_pairs, _ = self.inspect(compact)
            self.assertEqual(base_tags, compact_tags)
            self.assertEqual(compact_pairs, [pair for pair in base_pairs if pair[3] >= 20])
            for options in ({'min_tag_occurrences': 101}, {'exclude_tags': ['standing']}):
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'Tag filters differ'):
                    import_parquet(files, root / 'wrong.sqlite3', state_path=state, **options, progress=lambda _: None)
            self.assertFalse((root / 'wrong.sqlite3').exists())
            self.assertEqual(self.inspect(base), (base_tags, base_pairs, (500, 'ready')))

    def test_cli_profile_overrides_nested_inputs_and_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); raw = root / 'raw' / 'nested'; raw.mkdir(parents=True)
            self.make_files(raw)
            config = root / 'compact.json'
            config.write_text(json.dumps({'min_tag_occurrences': 201, 'min_cooccurrences': 50,
                'exclude_tags': ['black_hair']}), encoding='utf-8')
            target = root / 'library.sqlite3'; report = root / 'report.json'
            process = subprocess.run([sys.executable, '-m', 'corpus.importer', str(root / 'raw'), str(target),
                '--revision', 'smoke-v1', '--config', str(config), '--min-tag-occurrences', '200',
                '--min-cooccurrences', '10', '--exclude-tags', 'standing', '--exclude-tags', 'general',
                '--report', str(report), '--batch-size', '83', '--block-size', '2'],
                cwd=Path(__file__).resolve().parents[2], text=True, capture_output=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(result['revision'], 'smoke-v1')
            self.assertEqual(result['exclude_tags'], ['general', 'standing'])
            self.assertEqual(result['min_tag_occurrences'], 200)
            self.assertEqual(result['min_cooccurrence'], 10)
            self.assertEqual(result['post_count'], 500)
            self.assertEqual(len(result['inputs']), 2)
            self.assertIn(('black_hair', 200), self.inspect(target)[0])
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
                self.assertEqual({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}, {'tags', 'correlations', 'dataset'})
                self.assertFalse(db.execute('SELECT 1 FROM correlations c LEFT JOIN tags a ON c.tag_a=a.id LEFT JOIN tags b ON c.tag_b=b.id WHERE a.id IS NULL OR b.id IS NULL').fetchone())
            before = target.read_bytes()
            repeated = subprocess.run(process.args, cwd=Path(__file__).resolve().parents[2], text=True, capture_output=True)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(target.read_bytes(), before)
            from backend.paths import DataPaths
            from backend.store.candidate_libraries import CandidateLibraries
            from backend.store.candidate import SQLiteCandidateStore
            paths = DataPaths(root / 'application-data').ensure()
            libraries = CandidateLibraries(paths)
            added = libraries.add(target, 'processed.sqlite3')
            selected = libraries.select(added['filename'])
            runtime = SQLiteCandidateStore(paths.candidate_database, selected)
            self.assertEqual(added['tag_count'], result['tag_count'])
            self.assertEqual(runtime.dataset_status()['min_cooccurrence'], 10)

    def test_rejects_invalid_profile_and_unrecorded_state(self):
        from corpus.importer import processing_options
        for options in ({'min_cooccurrences': 0}, {'min_tag_occurrences': True},
                        {'min_cooccurrences': 2**53}, {'exclude_tags': 'standing'}, {'typo': 20}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                processing_options(options)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); files = self.make_files(root); state = root / 'old.sqlite3'
            with closing(sqlite3.connect(state)) as db, db:
                db.execute('CREATE TABLE source(source TEXT,revision TEXT)')
                db.execute("INSERT INTO source VALUES('old','v1')")
            with self.assertRaisesRegex(ValueError, 'no recorded processing parameters'):
                import_parquet(files, root / 'output.sqlite3', state_path=state, progress=lambda _: None)
            with closing(sqlite3.connect(state)) as db:
                self.assertEqual(db.execute('SELECT * FROM source').fetchall(), [('old', 'v1')])


if __name__ == '__main__':
    unittest.main()
