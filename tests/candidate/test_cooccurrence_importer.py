import math
import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from backend.candidate.importer import import_parquet


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
            if index % 5 == 0:
                tags += ['every_fifth']
            rows.append((index, ' '.join(tags)))
        paths = []
        for number, chunk in enumerate((rows[:250] + [(0, 'discarded_duplicate')],
                                        [(249, 'discarded_cross_shard')] + rows[250:])):
            path = root / f'{number}.parquet'
            pq.write_table(pa.table({
                'id': [row[0] for row in chunk],
                'tag_string_general': [row[1] for row in chunk],
                'tag_string_character': ['character_only'] * len(chunk),
                'tag_string_artist': ['artist_only'] * len(chunk),
                'tag_string_copyright': ['copyright_only'] * len(chunk),
                'tag_string_meta': ['meta_only'] * len(chunk),
            }), path, row_group_size=160)
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
            tags, pairs, status = self.inspect(target)
            self.assertEqual(tags, [('black_hair', 200), ('every_fifth', 100), ('exact_100', 100), ('standing', 200)])
            self.assertEqual(status, (500, 'ready'))
            counts = dict(tags)
            for a, b, pmi, count in pairs:
                self.assertAlmostEqual(pmi, math.log2(count * 500 / (counts[a] * counts[b])))
            self.assertIn(('black_hair', 'standing', -3.0, 10), pairs)
            self.assertIn(('every_fifth', 'exact_100', 0.0, 20), pairs)
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


if __name__ == '__main__':
    unittest.main()
