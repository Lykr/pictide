"""Renamed tag snapshots preserve content identity and scoring boundaries."""
from dataclasses import asdict
import hashlib
import json
import unittest

from backend.candidate.contracts import TagSnapshot


class TagSnapshotContractTests(unittest.TestCase):
    def test_category_rename_keeps_exact_historical_content_revision_and_feature_key(self):
        snapshot = TagSnapshot("rules:library.json", "scene", "forest", ("setting",))
        old_meaning = json.dumps({"text": "forest", "channel": "positive"}, ensure_ascii=False, sort_keys=True)
        old_revision = hashlib.sha256(old_meaning.encode("utf-8")).hexdigest()
        self.assertEqual(snapshot.content_revision, old_revision)
        self.assertEqual(snapshot.feature_key, ("rules:library.json", "scene", old_revision))
        recategorized = TagSnapshot(snapshot.source_id, snapshot.id, snapshot.text, ("location",))
        self.assertEqual(snapshot.feature_key, recategorized.feature_key)
        self.assertEqual(asdict(snapshot)["categories"], ("setting",))
        self.assertNotIn("tags", asdict(snapshot))



if __name__ == "__main__":
    unittest.main()
