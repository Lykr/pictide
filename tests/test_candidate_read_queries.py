"""Smoke the tuple reads used by incremental generation with an isolated library."""
from pathlib import Path
import tempfile
import unittest

from backend.store.candidate import SQLiteCandidateStore


class CandidateReadQueryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteCandidateStore(Path(self.directory.name) / "candidate.sqlite3")
        with self.store.connect() as db:
            db.executemany("INSERT INTO tags VALUES(?,?,?)", [
                (3, "three", 200), (1, "one", 300), (2, "two", 100)])
            db.executemany("INSERT INTO correlations VALUES(?,?,?,?)", [
                (1, 2, 1.0, 10), (2, 3, 2.0, 20), (1, 3, -0.5, 30),
                (2, 2, 5.0, 50)])

    def test_metadata_and_bidirectional_thresholds(self):
        self.assertEqual(self.store.generation_tags(), (
            (1, "one", 300), (2, "two", 100), (3, "three", 200)))
        self.assertEqual(dict(self.store.qualified_relations(2, 1.0, 10)), {1: 1.0, 3: 2.0})
        self.assertEqual(dict(self.store.qualified_relations(2, 1.1, 10)), {3: 2.0})
        self.assertEqual(dict(self.store.qualified_relations(2, 1.0, 11)), {3: 2.0})
        self.assertEqual(self.store.qualified_relations(1, 0.0, 10, [3]), ())
        self.assertEqual(dict(self.store.qualified_relations(2, 1.0, 10, [1, 2])), {1: 1.0})
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT name FROM tags WHERE id=1").fetchone()["name"], "one")

    def test_empty_restriction_and_chunked_ids(self):
        self.assertEqual(self.store.qualified_relations(2, 0, 10, []), ())
        self.assertEqual(self.store.qualified_relations(2, 0, 10, {2}), ())
        with self.store.connect() as db:
            db.executemany("INSERT INTO correlations VALUES(?,?,?,?)", [
                (2, identifier, 1.5, 10) for identifier in range(10, 811)])
        remaining = {1, 2, 3, *range(10, 811)}
        result = self.store.qualified_relations(2, 1.0, 10, remaining)
        expected = {1: 1.0, 3: 2.0, **dict.fromkeys(range(10, 811), 1.5)}
        self.assertIsInstance(result, tuple)
        self.assertTrue(all(type(row) is tuple for row in result))
        self.assertEqual(dict(result), expected)
        self.assertEqual(len(result), len(expected))


if __name__ == "__main__":
    unittest.main()
