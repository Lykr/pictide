"""Small neutral smoke coverage for SQLite cooccurrence candidates."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from backend.candidate.errors import CandidateError
from backend.candidate.service import CandidateService
from backend.store.candidate import SQLiteCandidateStore


class CooccurrenceSmoke(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/"candidate.sqlite3"
        self.service = CandidateService(SQLiteCandidateStore(self.path))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO dataset VALUES(1,'neutral-fixture','v1',100,'ready')")
            db.executemany("INSERT INTO tags VALUES(?,?,?)", [
                (1,"blue_sky",100),
                (2,"green_grass",100),
                (3,"soft_light",100),
                (4,"wide_view",100),
                (5,"night",100)])
            db.executemany("INSERT INTO correlations VALUES(?,?,?,?)", [
                (1,2,1.0,80),(1,3,1.0,80),(1,4,1.0,80),(2,3,1.0,80),(2,4,1.0,80),(3,4,1.0,80),(1,5,10.0,1)])
        self.doc = dict(base_positive=["blue sky"],base_negative=["blurry"],
                        min_tags=3,max_tags=3,pmi_threshold=0.5,min_cooccurrence=5,
                        change_budget=2)
        self.service.save_preset(dict(id="test",name="neutral",document=self.doc))

    def tearDown(self):
        self.directory.cleanup()

    def test_anchor_pmi_and_seed(self):
        options = dict(preset_id="test",mode="fixed_seed",seed=19)
        a = self.service.generate(options)
        self.assertEqual(a,self.service.generate(options))
        self.assertNotIn("night",a["positive"])
        self.assertTrue(a["positive"].startswith("blue sky, "))
        self.assertEqual(a["negative"],"blurry")
        self.assertEqual(a["report"]["tag_count"],3)
        self.assertEqual(len(self.service.provider.generate(options,{"count":2})),2)
        self.assertEqual(self.service.list_tags("blue sky")["total"],1)
        self.assertEqual(set(self.service.list_tags()["tags"][0]), {"id", "name", "post_count"})
        self.assertIn("pmi-v1:general:min100", a["source_id"])
        self.assertEqual(a["selected_tags"][0]["categories"], ["general"])
        self.assertEqual(self.service.store.find_tag("blue_sky"), self.service.store.find_tag("blue sky"))
        with self.service.store.connect() as db:
            db.execute("UPDATE correlations SET pmi=2 WHERE tag_a=1 AND tag_b=2")
            db.execute("UPDATE correlations SET pmi=-1 WHERE tag_a=1 AND tag_b=4")
        anchor = self.service.store.find_tag("blue_sky")
        weights = {tag["id"]: weight for tag, weight in self.service.store.expansion_candidates([anchor], -1, 5)}
        self.assertEqual(set(weights), {2, 3, 4})  # High PMI with count=1 is still excluded.
        self.assertAlmostEqual(weights[2]/weights[3], 2.0)
        self.assertAlmostEqual(weights[2]/weights[4], 8.0)
        other = self.service.store.find_tag("green_grass")
        self.assertNotIn(5, {tag["id"] for tag, _ in self.service.store.expansion_candidates([anchor, other], -10, 1)})
        negative_threshold = dict(self.doc, pmi_threshold=-1)
        self.assertTrue(self.service.generate(dict(options, document=negative_threshold))["positive"])

    def test_uniform_target_length_and_unreachable_target(self):
        document = dict(self.doc, min_tags=2, max_tags=4)
        counts = {length: 0 for length in range(2, 5)}
        for seed in range(300):
            result = self.service.generate(dict(preset_id="test", mode="fixed_seed", seed=seed, document=document))
            counts[result["report"]["tag_count"]] += 1
            self.assertEqual(result["report"]["stop_reason"], "target_length")
        # Fixed seeds give a repeatable smoke check that lengths do not pile up at the cap.
        self.assertTrue(all(75 <= count <= 125 for count in counts.values()), counts)
        with self.assertRaisesRegex(CandidateError, "随机目标长度 5"):
            self.service.generate(dict(preset_id="test", mode="fixed_seed", seed=5,
                                      document=dict(document, min_tags=3, max_tags=5), max_steps=20))

    def test_relation_lookup_distinguishes_unknown_zero_and_negative(self):
        with self.service.store.connect() as db:
            db.execute("UPDATE correlations SET pmi=-2 WHERE tag_a=1 AND tag_b=3")
        result = self.service.relations("blue sky", ["blue_sky", "green grass", "green_grass", "soft light", "custom, complete phrase"])
        self.assertTrue(result["anchor"]["known"])
        self.assertEqual(len(result["relations"]), 3)
        pairs = {row["text"]: row for row in result["relations"]}
        self.assertEqual(pairs["green grass"]["count"], 80)
        self.assertEqual(pairs["soft light"]["pmi"], -2)
        self.assertEqual(pairs["custom, complete phrase"], dict(text="custom, complete phrase", known=False, pmi=None, count=None))
        reverse = self.service.relations("green grass", ["blue sky", "night"])["relations"]
        self.assertEqual(reverse[0]["pmi"], 1)
        self.assertEqual(reverse[1], dict(text="night", known=True, pmi=None, count=0))
        unknown = self.service.relations("custom anchor", ["blue sky"])
        self.assertFalse(unknown["anchor"]["known"])
        self.assertIsNone(unknown["relations"][0]["count"])

    def test_vocabulary_defaults_to_fifteen_and_supports_page_jump(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany("INSERT INTO tags VALUES(?,?,?)", [
                (index, f"neutral_{index}", 100)
                for index in range(6, 21)])
        first = self.service.list_tags()
        second = self.service.list_tags(page=2)
        self.assertEqual((first["page_size"], first["total"], len(first["tags"])), (15, 20, 15))
        self.assertEqual((second["page"], len(second["tags"])), (2, 5))
        self.assertFalse({tag["id"] for tag in first["tags"]} & {tag["id"] for tag in second["tags"]})
        self.assertEqual(len(self.service.list_tags(page_size=3)["tags"]), 3)

    def test_sequence_replay_budget_and_controls(self):
        options = dict(preset_id="test",mode="sequence",seed=9,sequence_step=0)
        previous = self.service.generate(options)
        for step in range(1,5):
            current = self.service.generate(dict(options,sequence_step=step))
            a={tag["id"] for tag in previous["selected_tags"]}
            b={tag["id"] for tag in current["selected_tags"]}
            self.assertLessEqual(len(a^b),2)
            previous=current
        fresh=CandidateService(SQLiteCandidateStore(self.path))
        self.assertEqual(previous,fresh.generate(dict(options,sequence_step=4)))
        locked=dict(self.doc,change_budget=0)
        first=self.service.generate(dict(options,document=locked))
        last=self.service.generate(dict(options,document=locked,sequence_step=8))
        self.assertEqual(first["positive"],last["positive"])
        rounds,next_options=self.service.prepare_rounds(dict(options,step_control="increment"),2)
        self.assertEqual([r["sequence"]["step"] for r in rounds],[0,1])
        self.assertEqual(next_options["sequence_step"],2)

    def test_variable_length_sequence_respects_single_change_budget(self):
        document = dict(self.doc, min_tags=2, max_tags=4, change_budget=1)
        options = dict(preset_id="test", mode="sequence", seed=9, document=document)
        previous = self.service.generate(options)
        for step in range(1, 12):
            current = self.service.generate(dict(options, sequence_step=step))
            a = {tag["id"] for tag in previous["selected_tags"]}
            b = {tag["id"] for tag in current["selected_tags"]}
            self.assertLessEqual(len(a ^ b), 1)
            self.assertIn(current["report"]["tag_count"], (2, 3, 4))
            previous = current
        fresh = CandidateService(SQLiteCandidateStore(self.path))
        self.assertEqual(previous, fresh.generate(dict(options, sequence_step=11)))

    def test_bounds_failure_and_free_fixed_text(self):
        with self.assertRaisesRegex(CandidateError, "min_tags"):
            self.service.generate(dict(preset_id="test",document=dict(self.doc,min_tags=0)))
        for invalid in (float("inf"), float("nan"), True):
            with self.assertRaisesRegex(CandidateError, "pmi_threshold"):
                self.service.generate(dict(preset_id="test",document=dict(self.doc,pmi_threshold=invalid)))
        minimal=dict(self.doc,base_positive=[],min_tags=1,max_tags=1)
        self.assertTrue(self.service.generate(dict(preset_id="test",document=minimal))["positive"])
        document=dict(self.doc,base_positive=["blue_sky","gentle atmosphere"],min_tags=2,max_tags=2)
        result=self.service.generate(dict(preset_id="test",mode="fixed_seed",document=document))
        self.assertEqual(result["positive"],"blue sky, gentle atmosphere")
        self.assertEqual(result["report"]["unrecognized_fixed"],["gentle atmosphere"])
        with self.assertRaises(CandidateError):
            self.service.generate(dict(preset_id="test",document=dict(self.doc,min_tags=5,max_tags=5),max_steps=8))
        with patch.object(self.service.store, "expansion_candidates", wraps=self.service.store.expansion_candidates) as candidates:
            with self.assertRaisesRegex(CandidateError, "起始候选"):
                self.service.generate(dict(preset_id="test",document=dict(self.doc,pmi_threshold=2)))
            self.assertEqual(candidates.call_count, 1)
        self.service.save_preset(dict(id="test",name="edited",document=self.doc))
        self.assertEqual(self.service.load_preset("test")["name"],"edited")


if __name__ == "__main__":
    unittest.main()
