import tempfile
import unittest
from pathlib import Path

from backend.domain import ValidationError
from backend.paths import DataPaths
from backend.store.roam_settings import RoamSettings
from backend.store.sqlite import Repository


class RoamOptionsStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.paths = DataPaths(self.directory.name).ensure()
        self.settings = RoamSettings(self.paths)

    def tearDown(self):
        self.directory.cleanup()

    def test_partial_options_preserve_selections_and_epoch_changes_only_with_scope(self):
        original = self.settings.save(8, 'backend', 'preset', 25, 9)
        self.assertFalse(original['liked_tags_only'])
        scoped = self.settings.save_options(liked_tags_only=True)
        self.assertNotEqual(scoped['epoch'], original['epoch'])
        for key in ('prefetch_count', 'max_history_images', 'backend_id', 'preset_id', 'playback_interval_seconds'):
            self.assertEqual(scoped[key], original[key])
        unchanged = self.settings.save_options(liked_tags_only=True, playback_interval=12)
        self.assertEqual(unchanged['epoch'], scoped['epoch'])
        self.assertEqual(unchanged['playback_interval_seconds'], 12)
        self.assertEqual(RoamSettings(self.paths).get(), unchanged)
        saved = self.settings.save(4, 'other-backend', 'other-preset', 10)
        self.assertTrue(saved['liked_tags_only'])
        self.assertEqual(saved['playback_interval_seconds'], 12)
        unscoped = self.settings.save_options(liked_tags_only=False)
        self.assertNotEqual(unscoped['epoch'], saved['epoch'])
        self.assertFalse(unscoped['liked_tags_only'])
        playback = self.settings.save_playback_interval(20)
        self.assertEqual(playback['epoch'], unscoped['epoch'])

    def test_defaults_and_strict_option_validation(self):
        self.assertIs(self.settings.get()['liked_tags_only'], False)
        interval_only = self.settings.save_options(playback_interval=10)
        self.assertEqual(interval_only['epoch'], '0' * 32)
        self.assertEqual(interval_only['prefetch_count'], 0)
        self.assertEqual(interval_only['playback_interval_seconds'], 10)
        for value in (0, 1, 'true', [], {}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.settings.save_options(liked_tags_only=value)
        for value in (0, 601, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.settings.save_options(liked_tags_only=True, playback_interval=value)
        self.assertFalse(self.settings.get()['liked_tags_only'])

    def test_liked_prompts_include_hidden_sources_and_track_feedback(self):
        repo = Repository(self.paths.database)
        repo.save_backend({'id': 'local', 'name': 'Local', 'kind': 'comfyui', 'base_url': 'http://localhost:8188', 'api_key': '', 'workflow': {}})
        images = []
        for index, positive in enumerate(('black hair, sunlight', 'black hair, sunlight', 'forest', 'deleted', 'disliked', 'unknown')):
            job = repo.create_job({'request_id': f'liked-pool-{index}', 'backend_id': 'local', 'positive': positive, 'negative': 'blurry', 'seed': index})
            repo.complete(job['id'], [{'node_id': '9', 'index': 0}])
            image = next(item for item in repo.artifacts() if item['job_id'] == job['id'])
            images.append(image['id'])
            if index < 4:
                repo.rate(image['id'], 1)
            elif index == 4:
                repo.rate(image['id'], -1)
            if index == 2:
                with repo.connection() as db:
                    db.execute('INSERT INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES(?,?,?,?)', (job['id'], 'epoch', '{}', image['created_at']))
        with repo.connection() as db:
            db.execute("UPDATE artifacts SET generated_hidden_at='hidden' WHERE id=?", (images[0],))
            db.execute("UPDATE artifacts SET roam_hidden_at='hidden' WHERE id=?", (images[2],))
            db.execute("UPDATE artifacts SET deleted_at='deleted' WHERE id=?", (images[3],))
            db.execute("INSERT INTO feedback VALUES(?,'other',1,'now')", (images[5],))
        self.assertEqual(repo.liked_positive_prompts(), ['black hair, sunlight', 'forest'])
        self.assertEqual(repo.liked_positive_prompts('other'), ['unknown'])
        repo.rate(images[0], None)
        self.assertEqual(repo.liked_positive_prompts(), ['black hair, sunlight', 'forest'])
        repo.rate(images[1], -1)
        self.assertEqual(repo.liked_positive_prompts(), ['forest'])
        repo.rate(images[2], None)
        self.assertEqual(repo.liked_positive_prompts(), [])


if __name__ == '__main__':
    unittest.main()
