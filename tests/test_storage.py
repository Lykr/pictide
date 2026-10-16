import tempfile
import unittest
import sqlite3
from pathlib import Path

from backend.candidate.contracts import TagSnapshot
from backend.domain import ConflictError, ValidationError, generation_fields
from backend.store.sqlite import Repository


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.directory.name)/"pictide.sqlite3")
        self.repo.save_backend({"id":"local","name":"First","kind":"comfyui","base_url":"http://localhost:8188","api_key":"secret","workflow":{}})
        self.payload = {"request_id":"request-123","backend_id":"local","positive":"library, warm light","negative":"blurry","seed":-1}

    def tearDown(self):
        self.directory.cleanup()

    def test_idempotent_random_seed_and_conflicting_retry(self):
        one = self.repo.create_job(self.payload)
        two = self.repo.create_job(self.payload)
        self.assertEqual(one["id"],two["id"])
        self.assertEqual(one["seed"],two["seed"])
        self.assertGreaterEqual(one["seed"],0)
        with self.assertRaises(ConflictError):
            self.repo.create_job({**self.payload,"positive":"something different"})

    def test_backend_edit_does_not_retarget_old_job(self):
        job = self.repo.create_job(self.payload)
        self.repo.save_backend({"id":"local","name":"Second","kind":"comfyui","base_url":"http://localhost:9999","api_key":"new-secret","workflow":{}})
        self.assertEqual(self.repo.job_backend(job["id"])["api_key"],"secret")
        self.assertEqual(self.repo.backend("local")["name"],"Second")

    def test_batch_outputs_feedback_retract_and_restart(self):
        job = self.repo.create_job(self.payload)
        outputs = [{"node_id":"9","index":n,"filename":f"image_{n}.png","subfolder":"","type":"output"} for n in range(2)]
        self.repo.complete(job["id"],outputs)
        self.repo.complete(job["id"],outputs)
        rows = self.repo.artifacts()
        self.assertEqual(len(rows),2)
        iid = rows[0]["id"]
        self.repo.rate(iid,1)
        self.repo.rate(iid,1)
        self.assertEqual(len(self.repo.artifacts(liked=True)),1)
        self.repo.rate(iid,None)
        self.assertEqual(len(self.repo.artifacts(liked=True)),0)
        self.assertIsNone(Repository(self.repo.path).artifact(iid)["feedback"])
        for value in (0, True, False, 1.0, "1", [], {}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.repo.rate(iid,value)
        self.assertIsNone(self.repo.artifact(iid)["feedback"])

    def test_signed_feedback_survives_reopen_and_remains_exclusive(self):
        job = self.repo.create_job(self.payload)
        self.repo.complete(job["id"], [{"node_id": "9", "index": 0}])
        iid = self.repo.artifacts()[0]["id"]
        self.repo.rate(iid, 1)
        self.repo.rate(iid, -1)
        reopened = Repository(self.repo.path)
        self.assertEqual(reopened.artifact(iid)["feedback"], -1)
        self.assertEqual(reopened.artifacts(liked=True), [])
        with reopened.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM feedback WHERE artifact_id=?", (iid,)).fetchone()[0], 1)
        reopened.rate(iid, None)
        self.assertIsNone(reopened.artifact(iid)["feedback"])

    def test_cancelled_submission_retains_id_but_never_enters_feed(self):
        job = self.repo.create_job(self.payload)
        self.repo.update_job(job["id"],"submitting")
        self.repo.update_job(job["id"],"cancelled")
        self.repo.attach_prompt(job["id"],"external-id")
        self.repo.update_job(job["id"],"running")
        self.repo.complete(job["id"],[{"node_id":"9","index":0}])
        self.assertEqual(self.repo.job(job["id"])["status"],"cancelled")
        self.assertEqual(self.repo.job(job["id"])["backend_prompt_id"],"external-id")
        self.assertEqual(self.repo.artifacts(),[])

    def test_recovery_does_not_queue_unknown_submission_again(self):
        job = self.repo.create_job(self.payload)
        self.repo.update_job(job["id"],"submitting")
        self.repo.recover_submissions()
        self.assertEqual(self.repo.job(job["id"])["status"],"unknown")
        self.assertIsNone(self.repo.next_job())

    def test_generation_validation_preserves_exact_text(self):
        text = "  library, warm light\n"
        fields = generation_fields({**self.payload,"positive":text})
        self.assertEqual(fields["positive"],text)
        for seed in [True,1.5,-2,2**53]:
            with self.assertRaises(ValidationError):
                generation_fields({**self.payload,"seed":seed})

    def test_queue_capacity(self):
        for n in range(10):
            self.repo.create_job({**self.payload,"request_id":f"request-{n}"})
        with self.assertRaises(ValidationError):
            self.repo.create_job({**self.payload,"request_id":"one-too-many"})

    def test_claim_submission_once(self):
        job = self.repo.create_job(self.payload)
        self.assertTrue(self.repo.claim_job(job["id"]))
        self.assertFalse(self.repo.claim_job(job["id"]))
        self.assertEqual(self.repo.job(job["id"])["status"],"submitting")

    def test_existing_database_is_migrated_without_losing_images_or_feedback(self):
        job = self.repo.create_job(self.payload)
        self.repo.complete(job["id"],[{"node_id":"9","index":0,"filename":"old.png"}])
        iid = self.repo.artifacts()[0]["id"]
        self.repo.rate(iid,1)
        with self.repo.connection() as db:
            db.execute("ALTER TABLE artifacts DROP COLUMN local_path")
            db.execute("ALTER TABLE artifacts DROP COLUMN content_type")
        migrated = Repository(self.repo.path)
        self.assertEqual(migrated.artifact(iid)["feedback"],1)
        self.assertEqual(migrated.job(job["id"])["status"],"completed")
        self.assertIsNone(migrated.artifact(iid)["local_path"])

    def test_pagination_and_old_favorites(self):
        job = self.repo.create_job(self.payload)
        self.repo.complete(job["id"],[{"node_id":"9","index":n,"filename":f"test{n}.png"} for n in range(205)])
        first = self.repo.artifacts(limit=200)
        second = self.repo.artifacts(limit=200,before=first[-1]["id"])
        self.assertEqual(len(first),200)
        self.assertEqual(len(second),5)
        self.assertFalse({x["id"] for x in first} & {x["id"] for x in second})
        old = second[-1]
        self.repo.rate(old["id"],1)
        self.assertEqual(self.repo.artifacts(liked=True)[0]["id"],old["id"])
        self.assertEqual(self.repo.counts(),{"artifacts":205,"liked":1,"roam":0,"generate":205})


class LibraryContractTests(unittest.TestCase):
    def test_text_edit_creates_new_feature_but_category_edit_preserves_historical_categories(self):
        old = TagSnapshot("library-a","scene.1","library",("scene",))
        edited = TagSnapshot("library-a","scene.1","office",("scene",))
        retagged = TagSnapshot("library-a","scene.1","library",("interior",))
        self.assertNotEqual(old.feature_key,edited.feature_key)
        self.assertEqual(old.feature_key,retagged.feature_key)
        self.assertEqual(old.categories,("scene",))
        self.assertNotEqual(old.feature_key,TagSnapshot("library-b","scene.1","library").feature_key)
        self.assertNotEqual(old.feature_key,TagSnapshot("library-a","scene.1","library",channel="negative").feature_key)
