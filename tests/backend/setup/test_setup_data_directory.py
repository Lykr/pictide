"""Confirm storage before initialization and retain the choice across launches."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from backend.setup.local_generation_session import prepare_windows_data_directory, prepare_windows_setup
from backend.paths import DataPaths, saved_data_directory


class SetupDataDirectorySmoke(unittest.TestCase):
    def test_redirected_startup_skips_menus_and_forced_setup_requires_a_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = DataPaths(Path(temporary) / 'data')
            with patch('backend.setup.local_generation_session.desktop_busy', return_value=False), \
                    patch('sys.stdin', Mock(isatty=lambda: True)), patch('sys.stdout', Mock(isatty=lambda: False)), \
                    patch('backend.setup.windows_ui.choose_data_directory') as choose, \
                    patch('backend.setup.windows_ui.run_setup') as setup:
                self.assertIs(prepare_windows_data_directory(paths), paths)
                self.assertTrue(prepare_windows_setup(paths))
                with self.assertRaisesRegex(RuntimeError, 'interactive terminal'):
                    prepare_windows_data_directory(paths, force=True)
                with self.assertRaisesRegex(RuntimeError, 'interactive terminal'):
                    prepare_windows_setup(paths, force=True)
            choose.assert_not_called()
            setup.assert_not_called()
            self.assertFalse(paths.root.exists())

    def test_host_cancel_precedes_runtime_creation_and_downloads(self):
        from backend.host import main
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch('backend.paths.launcher_settings_path', return_value=root / 'pictide.local.json'), \
                    patch('backend.setup.local_generation_session.interactive_terminal', return_value=True), \
                    patch('backend.setup.windows_ui.choose_data_directory', return_value=None), \
                    patch('backend.host.PictideApplication.prepare_startup') as startup:
                main(['--desktop', '--data-dir', str(root / 'data')])
                self.assertFalse((root / 'data').exists())
                self.assertFalse((root / 'pictide.local.json').exists())
                startup.assert_not_called()

    def test_cancel_then_confirm_external_directory_and_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'program'
            program.mkdir()
            original = DataPaths(program / 'data')
            selected = Path(temporary) / 'selected'
            settings = program / 'pictide.local.json'
            with patch('backend.paths.launcher_settings_path', return_value=settings), \
                    patch('backend.setup.local_generation_session.interactive_terminal', return_value=True), \
                    patch('backend.setup.local_generation_session.desktop_busy', return_value=False), \
                    patch('backend.setup.windows_ui.choose_data_directory', side_effect=[None, str(selected)]) as choose:
                self.assertIsNone(prepare_windows_data_directory(original))
                self.assertFalse(original.root.exists())
                self.assertFalse(settings.exists())
                result = prepare_windows_data_directory(original)
                self.assertEqual(result.root, selected)
                self.assertEqual(saved_data_directory(), selected)
                self.assertFalse(original.root.exists())
                self.assertTrue(result.models.is_dir())
                self.assertFalse(any(result.tmp.iterdir()))
                self.assertIs(prepare_windows_data_directory(result), result)
                self.assertEqual(choose.call_count, 2)

    def test_unwritable_choice_retries_and_keeps_original_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = DataPaths(root / 'data').ensure()
            old_image = original.images / 'keep.png'
            old_image.write_bytes(b'existing image')
            blocked = root / 'file'
            blocked.write_text('occupied')
            selected = root / 'new-data'
            with patch('backend.paths.launcher_settings_path', return_value=root / 'pictide.local.json'), \
                    patch('backend.setup.local_generation_session.interactive_terminal', return_value=True), \
                    patch('backend.setup.local_generation_session.desktop_busy', return_value=False), \
                    patch('backend.setup.windows_ui.choose_data_directory', side_effect=[str(blocked), str(selected)]) as choose:
                result = prepare_windows_data_directory(original, force=True)
                self.assertEqual(result.root, selected)
                self.assertTrue(choose.call_args.kwargs['error'])
                self.assertEqual(old_image.read_bytes(), b'existing image')
                self.assertFalse(any(result.images.iterdir()))


if __name__ == '__main__':
    unittest.main()
