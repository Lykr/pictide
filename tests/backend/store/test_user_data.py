import hashlib
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

from backend.domain import ConflictError, ValidationError
from backend.paths import DataPaths
from backend.recommendation import policy
from backend.store.user_data import export_user_data, import_user_data
from backend.store.recommendation import _decode, _encode
from backend.store.sqlite import Repository


class UserDataArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source_paths = DataPaths(Path(self.temporary.name) / "source").ensure()
        self.source = Repository(self.source_paths.database)
        self.source.save_backend({"id": "fixture", "name": "Fixture", "kind": "comfyui",
                                  "base_url": "http://127.0.0.1:8188", "api_key": "secret",
                                  "workflow": {}})
        self.feature_version = "feature-v1"

    def like(self, index=0):
        job = self.source.create_job({
            "request_id": f"user-data-{index}",
            "backend_id": "fixture",
            "positive": "garden, sunlight",
            "negative": "blurry",
            "seed": index,
        })
        image = self.source_paths.images / f"source-{index}.png"
        image.write_bytes(b"image-bytes-" + bytes([index]))
        self.source.complete(job["id"], [{
            "node_id": "9", "index": 0,
            "local_path": image.relative_to(self.source_paths.root).as_posix(),
            "content_type": "image/png",
        }])
        artifact = next(row for row in self.source.artifacts() if row["job_id"] == job["id"])
        self.source.rate(artifact["id"], 1)
        return artifact

    def export(self, *, include_liked=True, include_preferences=True):
        return export_user_data(self.source_paths, self.source, "1.2.0",
                                self.feature_version, policy.POLICY_VERSION,
                                include_liked=include_liked,
                                include_preferences=include_preferences)

    def test_export_and_import_round_trip_liked_image_data(self):
        artifact = self.like()
        archive, filename = self.export()
        self.assertRegex(filename, r"^pictide-user-data-\d{8}T\d{6}\.zip$")
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(set(bundle.namelist()), {
                "manifest.json", "data.json",
                f"images/{artifact['id']}.png",
                f"prompts/{artifact['id']}.json",
            })
            manifest = json.loads(bundle.read("manifest.json"))
            self.assertEqual(manifest["format"], "pictide-user-data")
            self.assertEqual(manifest["counts"]["liked_images"], 1)
            self.assertEqual(json.loads(bundle.read(f"prompts/{artifact['id']}.json")),
                             {"positive": "garden, sunlight", "negative": "blurry"})

        destination_paths = DataPaths(Path(self.temporary.name) / "destination").ensure()
        destination = Repository(destination_paths.database)
        result = import_user_data(destination_paths, destination, archive,
                                  self.feature_version, policy.POLICY_VERSION)
        self.assertEqual(result["liked_imported"], 1)
        self.assertEqual(result["liked_skipped"], 0)
        self.assertTrue((destination_paths.root / result["backup"]).is_file())
        imported = destination.artifacts(liked=True)
        self.assertEqual([item["id"] for item in imported], [artifact["id"]])
        self.assertEqual((destination_paths.root / imported[0]["local_path"]).read_bytes(),
                         b"image-bytes-\x00")
        self.assertEqual(imported[0]["positive"], "garden, sunlight")
        with destination.connection() as db:
            configuration = json.loads(db.execute("SELECT config FROM backend_revisions").fetchone()["config"])
        self.assertNotEqual(configuration["api_key"], "secret")
        self.assertEqual(configuration["api_key"], "")

    def test_version_one_archive_without_categories_remains_full_import(self):
        artifact = self.like()
        archive, _ = self.export()
        legacy = Path(self.temporary.name) / "legacy-user-data.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(legacy, "w") as target:
            data = json.loads(source.read("data.json"))
            data.pop("categories", None)
            data_bytes = json.dumps(data, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")
            manifest = json.loads(source.read("manifest.json"))
            manifest.pop("categories", None)
            for entry in manifest["files"]:
                if entry["path"] == "data.json":
                    entry["size"] = len(data_bytes)
                    entry["sha256"] = hashlib.sha256(data_bytes).hexdigest()
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode("utf-8")
            for info in source.infolist():
                content = (data_bytes if info.filename == "data.json"
                           else manifest_bytes if info.filename == "manifest.json"
                           else source.read(info.filename))
                target.writestr(info, content)
        destination_paths = DataPaths(Path(self.temporary.name) / "destination").ensure()
        destination = Repository(destination_paths.database)
        result = import_user_data(destination_paths, destination, legacy,
                                  self.feature_version, policy.POLICY_VERSION)
        self.assertEqual(result["categories"], {"liked_images": True, "preferences": True})
        self.assertEqual(result["liked_imported"], 1)
        self.assertEqual(destination.artifacts(liked=True)[0]["id"], artifact["id"])

    def test_repeated_import_skips_existing_liked_images(self):
        self.like()
        archive, _ = self.export()
        destination_paths = DataPaths(Path(self.temporary.name) / "destination").ensure()
        destination = Repository(destination_paths.database)
        import_user_data(destination_paths, destination, archive,
                         self.feature_version, policy.POLICY_VERSION)
        result = import_user_data(destination_paths, destination, archive,
                                  self.feature_version, policy.POLICY_VERSION)
        self.assertEqual((result["liked_imported"], result["liked_skipped"]), (0, 1))
        self.assertEqual(destination.counts()["liked"], 1)

    def test_historical_event_journal_does_not_inflate_export(self):
        artifact = self.like()
        candidate = json.dumps({
            "candidate_id": "candidate-1", "positive": "garden, sunlight",
            "negative": "blurry",
            "terms": [
                {"text": "garden", "channel": "positive"},
                {"text": "sunlight", "channel": "positive"},
                {"text": "blurry", "channel": "negative"},
            ],
        }, separators=(",", ":"))
        with self.source.connection() as db:
            for _ in range(200):
                db.execute("INSERT INTO recommendation_events(user_id,artifact_id,value,candidate) "
                           "VALUES ('local',?,1,?)", (artifact["id"], candidate))
            revision = db.execute("SELECT MAX(revision) FROM recommendation_events").fetchone()[0]
            db.execute("INSERT INTO recommendation_evidence VALUES ('local',?,?,?,?,?)",
                       (self.feature_version, artifact["id"], revision, 1, candidate))
        archive, _ = self.export()
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            data = json.loads(bundle.read("data.json"))
        self.assertEqual(manifest["counts"]["recommendation_events"], 1)
        self.assertEqual(len(data["recommendation"]["events"]), 1)

    def test_images_only_export_leaves_unselected_preferences_untouched(self):
        artifact = self.like()
        archive, _ = self.export(include_preferences=False)
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            data = json.loads(bundle.read("data.json"))
            names = set(bundle.namelist())
        self.assertEqual(manifest["categories"], {"liked_images": True, "preferences": False})
        self.assertIsNone(data["recommendation"])
        self.assertNotIn("state/precision.bin", names)

        destination_paths = DataPaths(Path(self.temporary.name) / "destination").ensure()
        destination = Repository(destination_paths.database)
        with destination.connection() as db:
            db.execute("INSERT INTO recommendation_learning_boundaries VALUES ('local',7,'marker')")
        result = import_user_data(destination_paths, destination, archive,
                                  self.feature_version, policy.POLICY_VERSION)
        self.assertEqual(result["liked_imported"], 1)
        self.assertEqual(result["preference_evidence"], 0)
        with destination.connection() as db:
            boundary = db.execute("SELECT event_floor FROM recommendation_learning_boundaries "
                                  "WHERE user_id='local'").fetchone()[0]
        self.assertEqual(boundary, 7)
        self.assertEqual(destination.artifacts(liked=True)[0]["id"], artifact["id"])

    def test_preferences_only_export_has_no_images_and_sets_learning_boundary(self):
        artifact = self.like()
        candidate = json.dumps({
            "candidate_id": "candidate-1", "positive": "garden, sunlight",
            "negative": "blurry",
            "terms": [
                {"text": "garden", "channel": "positive"},
                {"text": "sunlight", "channel": "positive"},
                {"text": "blurry", "channel": "negative"},
            ],
        }, separators=(",", ":"))
        with self.source.connection() as db:
            db.execute("INSERT INTO recommendation_events(user_id,artifact_id,value,candidate) "
                       "VALUES ('local',?,1,?)", (artifact["id"], candidate))
            revision = db.execute("SELECT MAX(revision) FROM recommendation_events").fetchone()[0]
            db.execute("INSERT INTO recommendation_evidence VALUES ('local',?,?,?,?,?)",
                       (self.feature_version, artifact["id"], revision, 1, candidate))
        archive, _ = self.export(include_liked=False)
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            data = json.loads(bundle.read("data.json"))
            names = set(bundle.namelist())
        self.assertEqual(manifest["categories"], {"liked_images": False, "preferences": True})
        self.assertEqual(data["liked"], [])
        self.assertFalse(any(name.startswith("images/") for name in names))

        destination_paths = DataPaths(Path(self.temporary.name) / "destination").ensure()
        destination = Repository(destination_paths.database)
        result = import_user_data(destination_paths, destination, archive,
                                  self.feature_version, policy.POLICY_VERSION)
        self.assertEqual(result["liked_imported"], 0)
        self.assertEqual(result["preference_evidence"], 1)
        self.assertEqual(destination.counts()["liked"], 0)
        with destination.connection() as db:
            self.assertIsNotNone(db.execute("SELECT 1 FROM recommendation_learning_boundaries "
                                            "WHERE user_id='local' AND event_floor>=1").fetchone())
            self.assertEqual(db.execute("SELECT count(*) FROM recommendation_evidence").fetchone()[0], 1)

    def test_export_requires_at_least_one_category(self):
        with self.assertRaisesRegex(ValidationError, "at least one"):
            self.export(include_liked=False, include_preferences=False)

    def test_checksum_and_policy_mismatch_make_no_database_changes(self):
        artifact = self.like()
        archive, _ = self.export()
        corrupted = Path(self.temporary.name) / "corrupted.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupted, "w") as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == f"images/{artifact['id']}.png":
                    content = b"changed"
                target.writestr(info, content)
        destination_paths = DataPaths(Path(self.temporary.name) / "destination").ensure()
        destination = Repository(destination_paths.database)
        with self.assertRaisesRegex(ValidationError, "checksum mismatch"):
            import_user_data(destination_paths, destination, corrupted,
                             self.feature_version, policy.POLICY_VERSION)
        self.assertEqual(destination.counts()["liked"], 0)
        with self.assertRaisesRegex(ValidationError, "incompatible"):
            import_user_data(destination_paths, destination, archive,
                             self.feature_version, "another-policy")
        self.assertEqual(destination.counts()["liked"], 0)

    def test_feature_mismatch_imports_events_for_current_model_rebuild(self):
        artifact = self.like()
        candidate = json.dumps({
            "candidate_id": "candidate-1", "positive": "garden, sunlight",
            "negative": "blurry",
            "terms": [
                {"text": "garden", "channel": "positive"},
                {"text": "sunlight", "channel": "positive"},
                {"text": "blurry", "channel": "negative"},
            ],
        }, separators=(",", ":"))
        with self.source.connection() as db:
            db.execute("INSERT INTO recommendation_events(user_id,artifact_id,value,candidate) "
                       "VALUES ('local',?,1,?)", (artifact["id"], candidate))
            revision = db.execute("SELECT MAX(revision) FROM recommendation_events").fetchone()[0]
            db.execute("INSERT INTO recommendation_evidence VALUES ('local',?,?,?,?,?)",
                       (self.feature_version, artifact["id"], revision, 1, candidate))
        archive, _ = self.export()
        destination_paths = DataPaths(Path(self.temporary.name) / "destination").ensure()
        destination = Repository(destination_paths.database)
        result = import_user_data(destination_paths, destination, archive,
                                  "current-feature", policy.POLICY_VERSION)
        self.assertTrue(result["preference_rebuild_required"])
        self.assertEqual(result["liked_imported"], 1)
        with destination.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM recommendation_events").fetchone()[0], 1)
            imported_candidate = db.execute("SELECT candidate FROM recommendation_events").fetchone()["candidate"]
            self.assertEqual(db.execute("SELECT count(*) FROM recommendation_evidence").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM recommendation_policy").fetchone()[0], 0)
        self.assertEqual(imported_candidate, _encode(_decode(imported_candidate)))

    def test_import_waits_for_active_generation_tasks(self):
        self.like()
        archive, _ = self.export()
        destination_paths = DataPaths(Path(self.temporary.name) / "destination").ensure()
        destination = Repository(destination_paths.database)
        destination.save_backend({"id": "fixture", "name": "Fixture", "kind": "comfyui",
                                  "base_url": "http://127.0.0.1:8188", "api_key": "",
                                  "workflow": {}})
        destination.create_job({"request_id": "active", "backend_id": "fixture",
                                "positive": "garden", "negative": "", "seed": 1})
        with self.assertRaisesRegex(ConflictError, "Finish running"):
            import_user_data(destination_paths, destination, archive,
                             self.feature_version, policy.POLICY_VERSION)
        self.assertEqual(destination.counts()["liked"], 0)

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "Preference matrix checks need numpy")
    def test_complete_learned_preference_state_is_restored(self):
        import numpy as np
        from backend.recommendation.features import SEMANTIC_DIMENSION

        artifact = self.like()
        candidate = json.dumps({
            "candidate_id": "candidate-1", "positive": "garden, sunlight",
            "negative": "blurry",
            "terms": [
                {"text": "garden", "channel": "positive"},
                {"text": "sunlight", "channel": "positive"},
                {"text": "blurry", "channel": "negative"},
            ],
        }, separators=(",", ":"))
        record = policy.encode((), np.eye(SEMANTIC_DIMENSION), np.zeros(SEMANTIC_DIMENSION), 1, 1)
        with self.source.connection() as db:
            db.execute("INSERT INTO recommendation_events(user_id,artifact_id,value,candidate) "
                       "VALUES ('local',?,1,?)", (artifact["id"], candidate))
            revision = db.execute("SELECT MAX(revision) FROM recommendation_events").fetchone()[0]
            db.execute("INSERT INTO recommendation_policy VALUES ('local',?,?,?,?,?,?)",
                       (self.feature_version, record.revision, json.dumps(record.term_keys),
                        record.precision, record.reward, record.evidence_count))
            db.execute("INSERT INTO recommendation_evidence VALUES ('local',?,?,?,?,?)",
                       (self.feature_version, artifact["id"], revision, 1, candidate))
        archive, _ = self.export()
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
        self.assertIn("state/precision.bin", names)
        self.assertIn("state/reward.bin", names)
        destination_paths = DataPaths(Path(self.temporary.name) / "destination").ensure()
        destination = Repository(destination_paths.database)
        result = import_user_data(destination_paths, destination, archive,
                                  self.feature_version, policy.POLICY_VERSION)
        self.assertEqual(result["preference_evidence"], 1)
        with destination.connection() as db:
            state = db.execute("SELECT revision,evidence_count FROM recommendation_policy "
                               "WHERE user_id='local' AND feature_version=?", (self.feature_version,)).fetchone()
            evidence = db.execute("SELECT count(*) FROM recommendation_evidence WHERE user_id='local' "
                                  "AND feature_version=?", (self.feature_version,)).fetchone()[0]
        self.assertEqual((state["revision"], state["evidence_count"], evidence), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
