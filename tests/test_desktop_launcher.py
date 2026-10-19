"""Progress processes exit after readiness; failures and no-tray fallback stay visible."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.desktop_launcher import STATUS_ENV, launch_desktop


@unittest.skipUnless(sys.platform == 'win32', 'Windows desktop process creation')
class DesktopLauncherSmoke(unittest.TestCase):
    def test_windowless_worker_outlives_progress_process(self):
        with tempfile.TemporaryDirectory() as directory:
            def start(command, **options):
                self.assertIn('--desktop-worker', command)
                self.assertEqual(options['creationflags'], 0x08000000)
                Path(options['env'][STATUS_ENV]).write_text('ready', encoding='utf-8')
                return process
            process = Mock()
            process.poll.return_value = None
            with patch('backend.desktop_launcher.subprocess.Popen', side_effect=start):
                self.assertTrue(launch_desktop(['--desktop'], SimpleNamespace(tmp=Path(directory))))
            process.terminate.assert_not_called()

    def test_failed_or_unavailable_tray_does_not_silently_leave_a_worker(self):
        for status, code in (('console', 0), ('', 1)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                process = Mock(returncode=code)
                process.poll.return_value = code
                def start(command, **options):
                    Path(options['env'][STATUS_ENV]).write_text(status, encoding='utf-8')
                    return process
                with patch('backend.desktop_launcher.subprocess.Popen', side_effect=start), \
                        patch('backend.desktop_launcher.sys.stdin', None):
                    if status == 'console':
                        self.assertFalse(launch_desktop(['--desktop'], SimpleNamespace(tmp=Path(directory))))
                    else:
                        with self.assertRaises(SystemExit) as result:
                            launch_desktop(['--desktop'], SimpleNamespace(tmp=Path(directory)))
                        self.assertEqual(result.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
