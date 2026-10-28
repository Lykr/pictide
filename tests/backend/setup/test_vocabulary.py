"""Startup vocabulary choices, verified downloads, and offline reuse with neutral fixtures."""
from contextlib import closing
import hashlib
import io
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend import host
from backend.paths import DataPaths
from backend.setup.vocabulary import choose_vocabulary, prepare_vocabulary, vocabulary_catalog
from backend.store.candidate_libraries import CandidateLibraries
from backend.desktop.terminal import ANIMATION_ENV, clean
from tests.backend.candidate.test_candidate_libraries import vocabulary


class Response(io.BytesIO):
    def __init__(self, payload, *, offset=0, total=None):
        super().__init__(payload)
        self.status = 206 if offset else 200
        self.headers = {'Content-Range': f'bytes {offset}-{total - 1}/{total}'} if offset else {}


class VocabularyPreparationSmoke(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.paths = DataPaths(self.root / 'data').ensure()
        self.payload = vocabulary(self.root / 'neutral.sqlite3').read_bytes()
        self.item = {'bytes': len(self.payload), 'sha256': hashlib.sha256(self.payload).hexdigest()}
        self.catalog = {'release_tag': 'corpus-editions-fixture', 'editions': {
            edition: {'file': dict(self.item, path=f'pictide-vocabulary-{edition}.sqlite3')}
            for edition in ('filtered', 'all-ratings')}}
        self.messages = []

    def prepare(self, edition=None, **kwargs):
        with patch('backend.setup.vocabulary.vocabulary_catalog', return_value=self.catalog):
            prepare_vocabulary(self.paths, edition, progress=self.messages.append, **kwargs)

    def partial(self, edition='filtered'):
        return self.paths.cache / 'downloads/vocabularies' / self.item['sha256'] / f'pictide-vocabulary-{edition}.sqlite3.part'

    def test_first_download_selects_and_reuses_offline_without_touching_personal_data(self):
        self.paths.database.write_bytes(b'personal history fixture')
        with patch('backend.setup.vocabulary.urlopen', return_value=Response(self.payload)) as download:
            self.prepare()
        self.assertIn('pictide-vocabulary-filtered.sqlite3', download.call_args.args[0].full_url)
        listing = CandidateLibraries(self.paths).listing()
        self.assertEqual(listing['selected'], 'pictide-vocabulary-filtered.sqlite3')
        with closing(sqlite3.connect(self.paths.libraries / listing['selected'])) as db:
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT count(*) FROM tags').fetchone()[0], 2)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='presets'").fetchone())
        with patch('backend.setup.vocabulary.urlopen', side_effect=AssertionError('offline reuse requested network')), \
                patch('builtins.input', side_effect=AssertionError('valid library prompted')):
            self.prepare('all-ratings', interactive=True)
        self.assertEqual(CandidateLibraries(self.paths).listing(), listing)
        self.assertEqual(self.paths.database.read_bytes(), b'personal history fixture')

    def test_noninteractive_defaults_to_filtered_without_reading_stdin(self):
        with patch('builtins.input', side_effect=AssertionError('unattended startup read stdin')):
            self.assertEqual(choose_vocabulary(self.paths), 'filtered')
            self.assertEqual(choose_vocabulary(self.paths, 'all-ratings'), 'all-ratings')

    def test_interactive_choice_uses_arrows_and_keeps_explicit_warning_visible(self):
        output = io.StringIO()
        with patch('backend.desktop.text.system_language', return_value='zh-CN'), patch('sys.stdout', output):
            selected = choose_vocabulary(self.paths, interactive=True,
                                         read=Mock(side_effect=['2', 'down', 'enter']))
        self.assertEqual(selected, 'all-ratings')
        self.assertIn('可能生成露骨内容', output.getvalue())
        self.assertIn('filtered', output.getvalue())
        with patch('sys.stdout', io.StringIO()):
            self.assertEqual(choose_vocabulary(self.paths, interactive=True, read=lambda: 'enter'), 'filtered')
            with self.assertRaises(KeyboardInterrupt):
                choose_vocabulary(self.paths, interactive=True, read=lambda: 'escape')

    def test_explicit_all_ratings_logs_warning_before_downloading(self):
        def response(*args, **kwargs):
            self.assertIn('可能生成露骨内容', '\n'.join(self.messages))
            return Response(self.payload)
        with patch('backend.desktop.text.system_language', return_value='zh-CN'), \
                patch('backend.setup.vocabulary.urlopen', side_effect=response):
            self.prepare('all-ratings')
        self.assertEqual(CandidateLibraries(self.paths).listing()['selected'], 'pictide-vocabulary-all-ratings.sqlite3')

    def test_default_all_ratings_download_keeps_warning_in_the_refreshed_frame(self):
        output = io.StringIO()
        with patch('backend.desktop.text.system_language', return_value='zh-CN'), \
                patch('backend.setup.vocabulary.vocabulary_catalog', return_value=self.catalog), \
                patch('backend.setup.vocabulary.urlopen', return_value=Response(self.payload)), \
                patch.dict(os.environ, {ANIMATION_ENV: '1'}), patch('sys.stdout', output):
            prepare_vocabulary(self.paths, 'all-ratings')
        frame = clean(output.getvalue().rsplit('\x1b[H', 1)[1])
        self.assertIn('可能生成露骨内容', frame)
        self.assertIn('词库已就绪', frame)
        self.assertEqual(CandidateLibraries(self.paths).listing()['selected'], 'pictide-vocabulary-all-ratings.sqlite3')

    def test_custom_library_is_valid_and_missing_selection_uses_another_existing_library(self):
        libraries = CandidateLibraries(self.paths)
        shutil.copyfile(self.root / 'neutral.sqlite3', self.paths.libraries / 'custom.sqlite3')
        libraries.select('custom.sqlite3')
        shutil.copyfile(self.root / 'neutral.sqlite3', self.paths.libraries / 'spare.sqlite3')
        (self.paths.libraries / 'custom.sqlite3').unlink()
        with patch('backend.setup.vocabulary.urlopen', side_effect=AssertionError('existing library redownloaded')):
            self.prepare(interactive=True)
        self.assertEqual(libraries.listing()['selected'], 'spare.sqlite3')

    def test_corrupt_and_unready_libraries_are_preserved_while_a_valid_one_is_downloaded(self):
        broken = self.paths.libraries / 'pictide-vocabulary-filtered.sqlite3'
        broken.write_bytes(b'preserve this invalid file')
        unready = vocabulary(self.paths.libraries / 'unready.sqlite3')
        with closing(sqlite3.connect(unready)) as db, db:
            db.execute("UPDATE dataset SET status='loading'")
        with patch('backend.setup.vocabulary.urlopen', return_value=Response(self.payload)):
            self.prepare()
        self.assertEqual(broken.read_bytes(), b'preserve this invalid file')
        self.assertEqual(CandidateLibraries(self.paths).listing()['selected'], 'pictide-vocabulary-filtered-2.sqlite3')

    def test_failed_start_keeps_partial_and_next_start_resumes_it(self):
        partial = self.partial()
        partial.parent.mkdir(parents=True)
        partial.write_bytes(self.payload[:1024])
        with patch('backend.setup.vocabulary.urlopen', side_effect=OSError('offline')), \
                patch('backend.setup.vocabulary.time.sleep'):
            with self.assertRaises(RuntimeError):
                self.prepare()
        self.assertEqual(partial.read_bytes(), self.payload[:1024])
        def response(request, **kwargs):
            self.assertEqual(request.get_header('Range'), 'bytes=1024-')
            return Response(self.payload[1024:], offset=1024, total=len(self.payload))
        with patch('backend.setup.vocabulary.urlopen', side_effect=response):
            self.prepare()
        self.assertFalse(partial.exists())
        self.assertTrue(CandidateLibraries(self.paths).listing()['selected'])

    def test_server_ignoring_range_replaces_the_partial_instead_of_appending(self):
        partial = self.partial()
        partial.parent.mkdir(parents=True)
        partial.write_bytes(self.payload[:1024])
        with patch('backend.setup.vocabulary.urlopen', return_value=Response(self.payload)):
            self.prepare()
        self.assertTrue(CandidateLibraries(self.paths).listing()['selected'])

    def test_checksum_failure_and_non_sqlite_payload_are_not_installed(self):
        for payload, correct_hash in ((b'x' * len(self.payload), False), (b'not sqlite', True)):
            with self.subTest(valid_hash=correct_hash):
                if correct_hash:
                    self.item.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
                    self.catalog['editions']['filtered']['file'].update(self.item)
                with patch('backend.setup.vocabulary.urlopen', side_effect=lambda *a, **k: Response(payload)), \
                        patch('backend.setup.vocabulary.time.sleep'):
                    with self.assertRaises(RuntimeError):
                        self.prepare()
                self.assertEqual(CandidateLibraries(self.paths).listing()['libraries'], [])

    def test_vocabulary_failure_stops_before_model_http_and_browser(self):
        with patch('backend.host.DataPaths.configure_runtime', return_value=self.paths), \
                patch('backend.setup.vocabulary.prepare_vocabulary', side_effect=RuntimeError('vocabulary unavailable')), \
                patch('backend.recommendation.resources.prepare_model') as model, \
                patch('backend.host.create_app') as create, patch('backend.host.web.run_app') as listen, \
                patch('backend.host.webbrowser.open') as browser:
            with self.assertRaises(SystemExit) as raised:
                host.main(['--cli', '--data-dir', str(self.paths.root)])
        self.assertEqual(raised.exception.code, 1)
        model.assert_not_called(); create.assert_not_called(); listen.assert_not_called(); browser.assert_not_called()

    def test_cli_flag_reaches_startup_without_prompting(self):
        app = host.web.Application()
        from types import SimpleNamespace
        app[host.APPLICATION] = SimpleNamespace(updates=SimpleNamespace(installation=None))
        with patch('backend.host.DataPaths.configure_runtime', return_value=self.paths), \
                patch('backend.host.PictideApplication.prepare_startup') as prepare, \
                patch('backend.host.create_app', return_value=app), patch('backend.host.web.run_app'), \
                patch('backend.host.sys.stdin', Mock(isatty=lambda: False)), \
                patch('builtins.input', side_effect=AssertionError('explicit CLI choice prompted')):
            host.main(['--cli', '--data-dir', str(self.paths.root), '--vocabulary', 'all-ratings'])
        self.assertEqual(prepare.call_args.kwargs, {'vocabulary': 'all-ratings', 'interactive': False})

    def test_windows_desktop_parent_passes_interactive_choice_to_hidden_worker(self):
        with patch('backend.host.sys.platform', 'win32'), \
                patch('backend.host.DataPaths.configure_runtime', return_value=self.paths), \
                patch('backend.setup.local_generation_session.prepare_windows_data_directory', return_value=self.paths), \
                patch('backend.setup.local_generation_session.prepare_windows_setup', return_value=True), \
                patch('backend.host.sys.stdin', Mock(isatty=lambda: True)), \
                patch('backend.host.sys.stdout', Mock(isatty=lambda: True, fileno=Mock(side_effect=io.UnsupportedOperation))), \
                patch('backend.desktop.terminal.read_key', side_effect=['down', 'enter']), \
                patch('backend.desktop.launcher.launch_desktop', return_value=True) as launch:
            host.main(['--desktop', '--data-dir', str(self.paths.root)])
        self.assertEqual(launch.call_args.args[0][-2:], ['--vocabulary', 'all-ratings'])

    def test_catalog_has_both_editions_pinned_to_release_and_file_hashes(self):
        catalog = vocabulary_catalog()
        self.assertEqual(catalog['release_tag'], 'corpus-editions-' + catalog['fingerprint'])
        self.assertEqual(set(catalog['editions']), {'filtered', 'all-ratings'})
        for edition, entry in catalog['editions'].items():
            self.assertEqual(entry['file']['path'], f'pictide-vocabulary-{edition}.sqlite3')
            self.assertGreater(entry['file']['bytes'], 0)
            self.assertRegex(entry['file']['sha256'], r'^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
