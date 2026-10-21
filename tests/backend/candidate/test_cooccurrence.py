"""Small neutral smoke coverage for SQLite cooccurrence candidates."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from backend.candidate.errors import CandidateError
from backend.candidate.service import CandidateService, validate_document
from backend.store.candidate import SQLiteCandidateStore


class CooccurrenceSmoke(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/"candidate.sqlite3"
        self.service = CandidateService(SQLiteCandidateStore(self.path))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO dataset VALUES(1,'neutral-fixture','v1',100,'ready',1)")
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
                        change_budget=2, blocked_keywords=[])
        self.service.save_preset(dict(id="test",name="neutral",document=self.doc))

    def tearDown(self):
        self.directory.cleanup()

    def test_blocked_keywords_normalize_validate_and_preserve_fixed(self):
        document = dict(self.doc, base_negative=["soft light", "blurry"],
                        blocked_keywords=["  BLUE_SKY  ", "blue sky", "", "  ", "SOFT__LIGHT", "VIEW"])
        normalized = validate_document(document)
        self.assertEqual(normalized["blocked_keywords"], ["blue sky", "soft light", "view"])
        saved = self.service.save_preset(dict(id="blocked", name="blocked", document=document))
        self.assertEqual(saved["document"], normalized)
        result = self.service.generate(dict(preset_id="blocked", mode="fixed_seed", seed=19))
        self.assertEqual(result["positive"], "blue sky, green grass")
        self.assertEqual(result["negative"], "soft light, blurry")
        self.assertEqual(result["report"]["stop_reason"], "no_eligible_tags")
        for invalid in (None, "hair", [1], [None], {}):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(CandidateError, "blocked_keywords"):
                validate_document(dict(self.doc, blocked_keywords=invalid))

    def test_blocked_keywords_filter_first_draw_and_keep_partial_results(self):
        document = dict(self.doc, base_positive=[], blocked_keywords=["sky", "grass", "light", "night"])
        result = self.service.generate(dict(preset_id="test", document=document, mode="fixed_seed", seed=19))
        self.assertEqual(result["positive"], "wide view")
        self.assertEqual(result["report"]["stop_reason"], "no_eligible_tags")
        document["blocked_keywords"].append("view")
        empty = self.service.generate(dict(preset_id="test", document=document, mode="fixed_seed", seed=19))
        self.assertEqual(empty["positive"], "")
        self.assertEqual(empty["negative"], "blurry")

    def test_blocked_keywords_restart_along_and_invalidate_sequence_cache(self):
        options = dict(preset_id="test", mode="sequence", seed=9,
                       document=dict(self.doc, change_budget=0))
        initial = self.service.generate(dict(options, sequence_step=5))
        variables = [term["text"] for term in initial["selected_tags"]
                     if term["channel"] == "positive" and term["text"] != "blue sky"]
        blocked = dict(options, document=dict(options["document"], blocked_keywords=variables))
        frame = self.service.generate(dict(blocked, sequence_step=5))
        self.assertTrue(all(text not in frame["positive"] for text in variables))
        fresh = CandidateService(SQLiteCandidateStore(self.path))
        self.assertEqual(frame, fresh.generate(dict(blocked, sequence_step=5)))
        reference = dict(candidate_id=initial["candidate_id"], positive=initial["positive"],
                         negative=initial["negative"], terms=initial["selected_tags"])
        with patch.object(self.service, "_advance", side_effect=AssertionError("blocked reference must restart")):
            along = self.service.provider.generate(blocked, dict(prompt_mode="along", previous_candidate=reference))[0]
        self.assertTrue(all(text not in along.positive for text in variables))
        stay = self.service.provider.generate(blocked, dict(prompt_mode="stay", previous_candidate=reference))[0]
        self.assertEqual(stay.positive, initial["positive"])

    def test_negative_terms_exclude_exact_sampled_matches_in_all_modes(self):
        document = dict(self.doc, base_negative=["  SOFT__LIGHT  ", "green_grass"],
                        min_tags=4, max_tags=4)
        for mode in ("random_each_run", "fixed_seed", "sequence"):
            with self.subTest(mode=mode):
                result = self.service.generate(dict(preset_id="test", document=document,
                    mode=mode, seed=19, sequence_step=3))
                self.assertEqual(set(result["positive"].split(", ")), {"blue sky", "wide view"})
                self.assertEqual(result["report"]["tag_count"], 2)
                self.assertNotIn("soft light", result["positive"])
        # No statistical anchor, limited liked pool, and threaded candidate pools use the same filter.
        first_draw = dict(document, base_positive=[])
        options = dict(preset_id="test", document=first_draw, mode="fixed_seed", seed=19)
        pool = self.service.provider.generate(options, {
            "count": 4, "allowed_positive_tags": ["soft_light", "green_grass", "wide_view"]})
        self.assertTrue(all(item.positive == "wide view" for item in pool))
        # Whole-term matching is distinct from blocked-keyword substring matching.
        exact = dict(self.doc, base_negative=["light"], min_tags=4, max_tags=4)
        result = self.service.generate(dict(preset_id="test", document=exact, mode="fixed_seed", seed=19))
        self.assertIn("soft light", result["positive"])
        # Explicit fixed positives are retained even when a user also lists them as negative.
        explicit = dict(document, base_negative=[*document["base_negative"], "blue_sky"])
        result = self.service.generate(dict(preset_id="test", document=explicit, mode="fixed_seed", seed=19))
        self.assertEqual(result["positive"], "blue sky, wide view")

    def test_negative_edits_invalidate_sequence_and_conflicting_along_reference(self):
        options = dict(preset_id="test", mode="sequence", seed=19, sequence_step=3,
                       document=dict(self.doc, change_budget=0))
        initial = self.service.generate(options)
        variables = [term["text"] for term in initial["selected_tags"]
                     if term["channel"] == "positive" and term["text"] != "blue sky"]
        document = dict(options["document"], base_negative=[text.upper().replace(" ", "_") for text in variables])
        changed = dict(options, document=document)
        frame = self.service.generate(changed)
        self.assertTrue(set(frame["positive"].split(", ")).isdisjoint(variables))
        fresh = CandidateService(SQLiteCandidateStore(self.path))
        self.assertEqual(frame, fresh.generate(changed))
        reference = dict(candidate_id=initial["candidate_id"], positive=initial["positive"],
                         negative=initial["negative"], terms=initial["selected_tags"])
        along = self.service.provider.generate(changed, dict(prompt_mode="along", previous_candidate=reference))[0]
        self.assertTrue(set(along.positive.split(", ")).isdisjoint(variables))
        stay = self.service.provider.generate(changed, dict(prompt_mode="stay", previous_candidate=reference))[0]
        self.assertEqual(stay.positive, initial["positive"])

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
        self.assertIn("pmi-v2:general+ratings:min100:pair10", a["source_id"])
        self.assertEqual(a["selected_tags"][0]["categories"], ["general"])
        self.assertEqual(self.service.store.find_tag("blue_sky"), self.service.store.find_tag("blue sky"))
        with self.service.store.connect() as db:
            db.execute("UPDATE correlations SET pmi=2 WHERE tag_a=1 AND tag_b=2")
            db.execute("UPDATE correlations SET pmi=-1 WHERE tag_a=1 AND tag_b=4")
        anchor = self.service.store.find_tag("blue_sky")
        prepared = self.service._prepare_generation(dict(options, document=dict(self.doc, pmi_threshold=-1)))
        weights = {tag["id"]: weight for tag, weight in prepared.expansion().choices()}
        self.assertEqual(set(weights), {2, 3, 4})  # High PMI with count=1 is still excluded.
        self.assertAlmostEqual(weights[2]/weights[3], 2.0)
        self.assertAlmostEqual(weights[2]/weights[4], 8.0)
        other = self.service.store.find_tag("green_grass")
        prepared = self.service._prepare_generation(dict(options, document=dict(self.doc,
            base_positive=["blue sky", "green grass"], pmi_threshold=-10, min_cooccurrence=1)))
        self.assertNotIn(5, {tag["id"] for tag, _ in prepared.expansion().choices()})
        negative_threshold = dict(self.doc, pmi_threshold=-1)
        self.assertTrue(self.service.generate(dict(options, document=negative_threshold))["positive"])

    def test_liked_pool_resolves_exactly_and_keeps_fixed_terms(self):
        pool = self.service.resolve_tag_pool([
            " blue sky , green_grass, blue_sky, (soft light:1.2), unknown, GREEN_GRASS",
            "soft_light, green grass"])
        self.assertEqual(pool, ("blue_sky", "green_grass", "soft_light"))
        self.assertEqual(self.service.resolve_tag_pool(["unknown", "(blue_sky:1.2)"]), ())
        document = dict(self.doc, base_positive=["blue sky", "gentle atmosphere"],
                        base_negative=["green grass", "blurry"], min_tags=4, max_tags=4)
        context = dict(preset_id="test", mode="fixed_seed", seed=19, document=document)
        with patch.object(self.service.store, "find_tags", wraps=self.service.store.find_tags) as resolve:
            candidates = self.service.provider.generate(context, {
                "count": 4, "allowed_positive_tags": ["soft_light"]})
            self.assertEqual(resolve.call_count, 1)  # Resolve IDs once for the whole combination pool.
        for candidate in candidates:
            self.assertEqual(candidate.positive, "blue sky, gentle atmosphere, soft light")
            self.assertEqual(candidate.negative, "green grass, blurry")
        # Only scope was supplied internally; saved/shared presets remain unchanged.
        self.assertEqual(self.service.load_preset("test")["document"], self.doc)

    def test_scope_none_empty_and_first_draw_preserve_partial_results(self):
        context = dict(preset_id="test", mode="fixed_seed", seed=19)
        expected = self.service.generate(context)
        unlimited = self.service.provider.generate(context, {"allowed_positive_tags": None})[0]
        self.assertEqual((unlimited.positive, unlimited.negative), (expected["positive"], expected["negative"]))
        empty = self.service.provider.generate(context, {"allowed_positive_tags": []})[0]
        self.assertEqual((empty.positive, empty.negative), ("blue sky", "blurry"))
        no_anchor = dict(context, document=dict(self.doc, base_positive=[]))
        first = self.service.provider.generate(no_anchor, {"allowed_positive_tags": ["wide_view"]})[0]
        self.assertEqual(first.positive, "wide view")
        self.assertEqual(self.service.provider.generate(no_anchor, {"allowed_positive_tags": []})[0].positive, "")
        # A pool member must still meet the fixed anchor's PMI/support threshold.
        incompatible = self.service.provider.generate(context, {"allowed_positive_tags": ["night"]})[0]
        self.assertEqual(incompatible.positive, "blue sky")
        partial = self.service.generate(dict(context, max_steps=1), allowed_positive_tag_ids=frozenset((2, 3)))
        self.assertEqual(partial["report"]["tag_count"], 2)
        self.assertEqual(partial["report"]["stop_reason"], "search_limit")

    def test_sequence_cache_is_scoped_and_replays_with_budget(self):
        options = dict(preset_id="test", mode="sequence", seed=9,
                       document=dict(self.doc, change_budget=0))
        previous = self.service.provider.generate(options, {"allowed_positive_tags": ["green_grass"]})[0]
        changed = self.service.provider.generate(dict(options, sequence_step=7), {
            "allowed_positive_tags": ["soft_light"]})[0]
        self.assertEqual(previous.positive, "blue sky, green grass")
        self.assertEqual(changed.positive, "blue sky, soft light")
        fresh = CandidateService(SQLiteCandidateStore(self.path))
        self.assertEqual(changed, fresh.provider.generate(dict(options, sequence_step=7), {
            "allowed_positive_tags": ["soft_light"]})[0])
        scoped = dict(options, document=dict(self.doc, min_tags=2, max_tags=3))
        previous_ids = None
        for step in range(4):
            frame = self.service.generate(dict(scoped, sequence_step=step),
                                          allowed_positive_tag_ids=frozenset((2, 3)))
            ids = {int(tag["id"]) for tag in frame["selected_tags"] if tag["channel"] == "positive"}
            self.assertTrue(ids <= {1, 2, 3})
            if previous_ids is not None:
                self.assertLessEqual(len(ids ^ previous_ids), 2)
            previous_ids = ids

    def test_roam_stay_preserves_complete_text_and_snapshot(self):
        reference = dict(candidate_id="original-combination", positive="custom phrase, blue sky",
                         negative="(blurry:1.2), old negative", terms=[
            dict(source_id="old-source", id="text:custom", text="custom phrase", categories=[], channel="positive"),
            dict(source_id="old-source", id="1", text="blue sky", categories=["general"], channel="positive"),
            dict(source_id="old-source", id="text:negative", text="(blurry:1.2), old negative", categories=[], channel="negative")])
        context = dict(preset_id="test", mode="sequence", sequence_step=999)
        with patch.object(self.service, "generate", side_effect=AssertionError("stay must not draw tags")):
            pool = self.service.provider.generate(context, dict(count=4, prompt_mode="stay",
                        previous_candidate=reference, allowed_positive_tags=[]))
        self.assertEqual(len(pool), 1)
        self.assertEqual((pool[0].id, pool[0].positive, pool[0].negative),
                         (reference["candidate_id"], reference["positive"], reference["negative"]))
        self.assertEqual([(term.source_id, term.id, term.text, term.categories, term.channel) for term in pool[0].terms],
                         [(term["source_id"], term["id"], term["text"], tuple(term["categories"]), term["channel"])
                          for term in reference["terms"]])
        with patch.object(self.service, "_sequence", side_effect=AssertionError("roam must not replay a sequence")):
            first = self.service.provider.generate(context, dict(prompt_mode="stay", previous_candidate=None))[0]
        self.assertTrue(first.positive.startswith("blue sky, "))
        self.assertEqual(first.negative, "blurry")

    def test_roam_along_pool_uses_same_selected_reference_and_budget(self):
        from dataclasses import asdict
        context = dict(preset_id="test", mode="fixed_seed", seed=19)
        initial = self.service.generate(context)
        reference = dict(candidate_id=initial["candidate_id"], positive=initial["positive"],
                         negative=initial["negative"], terms=initial["selected_tags"])
        previous = {term["text"] for term in reference["terms"] if term["channel"] == "positive"}
        with patch.object(self.service, "_advance", wraps=self.service._advance) as advance:
            pool = self.service.provider.generate(context, dict(count=4, prompt_mode="along", previous_candidate=reference))
        self.assertEqual(advance.call_count, 4)
        starts = [{tag["id"] for tag in call.args[3]} for call in advance.call_args_list]
        self.assertTrue(all(start == starts[0] for start in starts))
        for item in pool:
            positive = {term.text for term in item.terms if term.channel == "positive"}
            self.assertLessEqual(len(positive ^ previous), self.doc["change_budget"])
            self.assertEqual(item.negative, "blurry")
        # Choose an arbitrary scored member, not the pool's last member; it alone is next's origin.
        chosen = pool[1]
        reference = dict(candidate_id=chosen.id, positive=chosen.positive, negative=chosen.negative,
                         terms=[asdict(term) for term in chosen.terms])
        locked = dict(context, mode="sequence", sequence_step=999, document=dict(self.doc, change_budget=0))
        with patch.object(self.service, "_sequence", side_effect=AssertionError("roam must not replay a sequence")):
            following = self.service.provider.generate(locked, dict(count=3, prompt_mode="along", previous_candidate=reference))
        self.assertTrue(all(item.positive == chosen.positive for item in following))

    def test_roam_along_recognizes_normalized_deduplicated_fixed_terms(self):
        document = dict(self.doc, base_positive=["blue_sky", "blue sky", "gentle_atmosphere", "gentle atmosphere"],
                        min_tags=4, max_tags=4, change_budget=0)
        context = dict(preset_id="test", mode="fixed_seed", seed=19, document=document)
        initial = self.service.generate(context)
        reference = dict(candidate_id=initial["candidate_id"], positive=initial["positive"],
                         negative=initial["negative"], terms=initial["selected_tags"])
        with patch.object(self.service, "_initial", side_effect=AssertionError("valid reference must not restart")), \
             patch.object(self.service, "_advance", wraps=self.service._advance) as advance:
            item = self.service.provider.generate(context, dict(prompt_mode="along", previous_candidate=reference))[0]
        self.assertEqual(item.positive, initial["positive"])
        self.assertEqual(advance.call_args.args[1], 2)  # Actual fixed terms, after normalization and deduplication.
        self.assertEqual(len(advance.call_args.args[3]), 2)

    def test_roam_along_invalid_start_restarts_with_current_scope_and_fixed_terms(self):
        initial = self.service.generate(dict(preset_id="test", mode="fixed_seed", seed=19))
        reference = dict(candidate_id=initial["candidate_id"], positive=initial["positive"],
                         negative=initial["negative"], terms=initial["selected_tags"])
        context = dict(preset_id="test", mode="fixed_seed", seed=19, document=dict(self.doc, change_budget=0))
        # Scope no longer contains any old variable: restart, retaining the fixed anchor outside scope.
        with patch.object(self.service, "_advance", side_effect=AssertionError("out-of-scope start")):
            pool = self.service.provider.generate(context, dict(count=2, prompt_mode="along",
                        previous_candidate=reference, allowed_positive_tags=["night"]))
        self.assertTrue(all(item.positive == "blue sky" for item in pool))
        # Changed PMI invalidates the old variable combination too; return the valid partial result.
        with self.service.store.connect() as db:
            db.execute("DELETE FROM correlations")
        with patch.object(self.service, "_advance", side_effect=AssertionError("invalid PMI start")):
            item = self.service.provider.generate(context, dict(prompt_mode="along", previous_candidate=reference))[0]
        self.assertEqual(item.positive, "blue sky")
        self.assertEqual(item.negative, "blurry")

    def test_intersection_handles_large_pool_and_reverse_index(self):
        with self.service.store.connect() as db:
            db.execute("DELETE FROM correlations")
            db.execute("DELETE FROM tags")
            db.executemany("INSERT INTO tags VALUES(?,?,?)", [(1, "anchor_low", 1000), (1000, "anchor_high", 2000),
                *[(ident, f"candidate_{ident}", 100) for ident in range(2, 503)]])
            db.executemany("INSERT INTO correlations VALUES(?,?,?,?)", [
                *[(1, ident, .25, 100) for ident in range(2, 503)],
                *[(ident, 1000, -.1 if ident == 5 else .75, 9 if ident == 3 else 100) for ident in range(2, 503)]])
        anchors = [self.service.store.find_tag(name) for name in ("anchor_low", "anchor_high")]
        prepared = self.service._prepare_generation(dict(preset_id="test", mode="fixed_seed",
            document=dict(self.doc, base_positive=["anchor low", "anchor high"], pmi_threshold=0, min_cooccurrence=10)))
        choices = prepared.expansion().choices()
        self.assertEqual([tag["id"] for tag, _ in choices], [ident for ident in range(2, 503) if ident not in (3, 5)])
        self.assertTrue(all(weight == 1 for _, weight in choices))

    def test_uniform_target_length_and_unreachable_target(self):
        document = dict(self.doc, min_tags=2, max_tags=4)
        counts = {length: 0 for length in range(2, 5)}
        for seed in range(300):
            result = self.service.generate(dict(preset_id="test", mode="fixed_seed", seed=seed, document=document))
            counts[result["report"]["tag_count"]] += 1
            self.assertEqual(result["report"]["stop_reason"], "target_length")
        # Fixed seeds give a repeatable smoke check that lengths do not pile up at the cap.
        self.assertTrue(all(75 <= count <= 125 for count in counts.values()), counts)
        result = self.service.generate(dict(preset_id="test", mode="fixed_seed", seed=5,
                                            document=dict(document, min_tags=3, max_tags=5), max_steps=20))
        self.assertEqual(result["report"]["tag_count"], 4)
        self.assertEqual(result["report"]["stop_reason"], "no_eligible_tags")

    def test_search_limit_partial_sequence_keeps_budget_and_replays(self):
        document = dict(self.doc, min_tags=20, max_tags=20)
        options = dict(preset_id="test", document=document, mode="sequence", seed=8, max_steps=1)
        previous = self.service.generate(dict(options, sequence_step=0))
        self.assertEqual(previous["report"]["tag_count"], 2)
        self.assertEqual(previous["report"]["stop_reason"], "search_limit")
        for step in range(1, 4):
            current = self.service.generate(dict(options, sequence_step=step))
            before = {tag["id"] for tag in previous["selected_tags"]}
            after = {tag["id"] for tag in current["selected_tags"]}
            self.assertLessEqual(len(before ^ after), document["change_budget"])
            self.assertEqual(current["sequence"]["changes"], len(before ^ after))
            self.assertLessEqual(current["report"]["tag_count"], 4)
            previous = current
        fresh = CandidateService(SQLiteCandidateStore(self.path))
        self.assertEqual(previous, fresh.generate(dict(options, sequence_step=3)))
        limited = self.service.generate(dict(options, mode="fixed_seed"))
        self.assertEqual(limited["report"]["tag_count"], 2)
        self.assertEqual(limited, self.service.generate(dict(options, mode="fixed_seed")))

    def test_relation_lookup_distinguishes_unknown_omitted_and_negative(self):
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
        self.assertEqual(reverse[1], dict(text="night", known=True, pmi=None, count=None))
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
        result = self.service.generate(dict(preset_id="test",document=dict(self.doc,min_tags=5,max_tags=5),max_steps=8))
        self.assertEqual(result["report"]["tag_count"], 4)
        with patch.object(self.service.store, "qualified_relations", wraps=self.service.store.qualified_relations) as candidates:
            result = self.service.generate(dict(preset_id="test",document=dict(self.doc,pmi_threshold=2)))
            self.assertEqual(result["positive"], "blue sky")
            self.assertEqual(result["report"]["stop_reason"], "no_eligible_tags")
            self.assertEqual(candidates.call_count, 1)
        self.service.save_preset(dict(id="test",name="edited",document=self.doc))
        self.assertEqual(self.service.load_preset("test")["name"],"edited")

    def test_parallel_fixed_pool_preserves_seed_order_and_uses_multiple_workers(self):
        import threading
        context = dict(preset_id="test", mode="fixed_seed", seed=19)
        expected = tuple(self.service.provider.generate(dict(context, seed=19+i), {"count": 1})[0]
                         for i in range(4))
        original = self.service._generate_prepared
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        active, maximum = 0, 0
        def observed(*args, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                barrier.wait(timeout=3)
                return original(*args, **kwargs)
            finally:
                with lock:
                    active -= 1
        with patch.object(self.service, "_generate_prepared", side_effect=observed):
            actual = self.service.provider.generate(context, {"count": 4})
        self.assertEqual(actual, expected)
        self.assertGreaterEqual(maximum, 2)

    def test_sequence_pool_stays_ordered_and_worker_errors_propagate(self):
        context = dict(preset_id="test", mode="sequence", seed=19, sequence_step=2)
        with patch("backend.candidate.provider.ThreadPoolExecutor", side_effect=AssertionError("sequence must stay serial")):
            pool = self.service.provider.generate(context, {"count": 3})
        fresh = CandidateService(SQLiteCandidateStore(self.path))
        expected = tuple(fresh.provider.generate(dict(context, sequence_step=2+i), {"count": 1})[0]
                         for i in range(3))
        self.assertEqual(pool, expected)
        with patch.object(self.service, "_generate_prepared", side_effect=CandidateError("smoke failure")):
            with self.assertRaisesRegex(CandidateError, "smoke failure"):
                self.service.provider.generate(dict(context, mode="fixed_seed"), {"count": 3})


    def test_incremental_batch_reuses_base_and_restores_dropped_candidates(self):
        context = dict(preset_id="test", mode="fixed_seed", seed=19)
        with patch.object(self.service.store, "generation_tags", wraps=self.service.store.generation_tags) as metadata, \
             patch.object(self.service.store, "qualified_relations", wraps=self.service.store.qualified_relations) as relations:
            pool = self.service.provider.generate(context, {"count": 4})
        self.assertEqual(metadata.call_count, 1)
        self.assertEqual(sum(call.args[0] == 1 for call in relations.call_args_list), 1)
        self.assertLessEqual(relations.call_count, 5)
        with self.service.store.connect() as db:
            db.execute("DELETE FROM correlations WHERE tag_a=3 AND tag_b=4")
        prepared = self.service._prepare_generation(context)
        state = prepared.expansion()
        state.add(self.service.store.find_tag("soft light"))
        self.assertNotIn(4, {tag["id"] for tag, _ in state.choices()})
        # Removing that constraint rebuilds from the unmodified batch base.
        self.assertIn(4, {tag["id"] for tag, _ in prepared.expansion().choices()})
        self.assertEqual(len(pool), 4)

    def test_incremental_float_order_and_no_work_lazy_paths(self):
        fixed = dict(preset_id="test", mode="fixed_seed", document=dict(self.doc, min_tags=1, max_tags=1))
        with patch.object(self.service.store, "generation_tags", side_effect=AssertionError("unused metadata")), \
             patch.object(self.service.store, "qualified_relations", side_effect=AssertionError("unused graph")):
            self.assertEqual(self.service.generate(fixed)["positive"], "blue sky")
        with self.service.store.connect() as db:
            db.execute("DELETE FROM correlations")
            db.execute("DELETE FROM tags")
            db.executemany("INSERT INTO tags VALUES(?,?,?)", [(1,"anchor_a",300),(2,"anchor_b",100),
                           (3,"anchor_c",200),(4,"option_d",100),(5,"option_e",100)])
            db.executemany("INSERT INTO correlations VALUES(?,?,?,?)", [(1,3,0,100),(2,3,0,100),
                (1,4,1,100),(2,4,1e16,100),(3,4,-1e16,100),(1,5,0,100),(2,5,0,100),(3,5,0,100)])
        document = dict(self.doc, base_positive=["anchor a","anchor b"], pmi_threshold=-1e16)
        prepared = self.service._prepare_generation(dict(preset_id="test", document=document))
        state = prepared.expansion()
        state.add(self.service.store.find_tag("anchor c"))
        weights = {tag["id"]: weight for tag, weight in state.choices()}
        self.assertEqual(weights[4], 1)
        self.assertEqual(weights[5], 2.0 ** (-1/3))


if __name__ == "__main__":
    unittest.main()
