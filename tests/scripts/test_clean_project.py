"""Cleanup deletes only reviewed disposable entries in isolated Git fixtures."""
import copy
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from scripts.clean_project import SOURCES, apply_plan, main, make_plan


class CleanupSmoke(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        subprocess.run(['git', 'init', '--quiet', str(self.root)], check=True)

    def file(self, relative, content='fixture'):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return target

    def test_preview_age_protection_and_reviewed_deletion(self):
        disposable = [self.file('dev/cache/wheels/cached.whl'),
                      self.file('dev/verification/old/report.json'),
                      self.file('data/backups/frontend-old/dist/index.html')]
        keep = [self.file('data/db/pictide.sqlite3'), self.file('data/images/liked.png'),
                self.file('data/backups/personal/pictide.sqlite3'),
                self.file('dev/verification/model/model.onnx'),
                self.file('dev/verification/partial/model.onnx.part'),
                self.file('dev/verification/raw/input.parquet'),
                self.file('dev/datasets/raw.parquet'), self.file('dev/models/model.onnx'),
                self.file('dev/runtime/builder/python.exe'), self.file('releases/app.zip'),
                self.file('web/dist/index.html'), self.file('data/tmp/desktop.lock'),
                self.file('data/cache/cache.bin')]
        recent = self.file('dev/tmp/recent.txt')
        old = time.time() - 8 * 86400
        for file in disposable:
            os.utime(file, (old, old))
            parent = file.parent
            while parent != self.root:
                os.utime(parent, (old, old))
                parent = parent.parent
        plan = make_plan(self.root, list(SOURCES), 7)
        self.assertEqual({entry['path'] for entry in plan['entries']},
                         {'dev/cache/wheels', 'dev/verification/old', 'data/backups/frontend-old'})
        self.assertTrue(all(file.exists() for file in disposable + keep))
        self.assertEqual(apply_plan(self.root, plan), 3)
        self.assertTrue(all(not file.exists() for file in disposable))
        self.assertTrue(all(file.exists() for file in keep + [recent]))

    def test_changed_plan_or_escaped_path_fails_before_any_deletion(self):
        first = self.file('dev/cache/a/cached.txt')
        later = self.file('dev/cache/z/cached.txt')
        plan = make_plan(self.root, ['caches'], 0)
        later.write_text('changed since preview', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Changed since preview'):
            apply_plan(self.root, plan)
        self.assertTrue(first.exists())
        refreshed = make_plan(self.root, ['caches'], 0)
        for path in ('../../outside', 'data/db', str(first.resolve())):
            altered = copy.deepcopy(refreshed)
            altered['entries'][-1]['path'] = path
            with self.assertRaises(ValueError):
                apply_plan(self.root, altered)
            self.assertTrue(first.exists())
        refreshed['root'] = str(self.root / 'another-project')
        with self.assertRaisesRegex(ValueError, 'another project'):
            apply_plan(self.root, refreshed)

    def test_tracked_content_is_preserved_even_if_added_after_preview(self):
        file = self.file('dev/cache/example/important.txt')
        plan = make_plan(self.root, ['caches'], 0)
        subprocess.run(['git', '-C', str(self.root), 'add', 'dev/cache/example/important.txt'], check=True)
        with self.assertRaisesRegex(ValueError, 'Git-tracked'):
            apply_plan(self.root, plan)
        self.assertEqual(make_plan(self.root, ['caches'], 0)['entries'], [])
        self.assertTrue(file.exists())

    def test_links_and_linked_cleanup_roots_are_preserved(self):
        outside = self.root / 'keep'
        outside.mkdir()
        important = self.file('keep/important.txt')
        cache = self.root / 'dev/cache'
        cache.mkdir(parents=True)
        try:
            (cache / 'linked').symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest('OS cannot create fixture symlinks: ' + str(error))
        self.assertEqual(make_plan(self.root, ['caches'], 0)['entries'], [])
        plan = {'version': 1, 'root': str(self.root), 'entries': [
            {'group': 'caches', 'path': 'dev/cache/linked'}]}
        with self.assertRaisesRegex(ValueError, 'Link or junction'):
            apply_plan(self.root, plan)
        (self.root / 'dev/verification').symlink_to(outside, target_is_directory=True)
        self.assertEqual(make_plan(self.root, ['verification'], 0)['entries'], [])
        self.assertTrue(important.exists())

    def test_apply_rejects_preview_filters_instead_of_ignoring_them(self):
        for option in (['--groups', 'caches'], ['--older-than-days', '30']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(['--apply', 'never-read.json', *option])
            self.assertEqual(raised.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
