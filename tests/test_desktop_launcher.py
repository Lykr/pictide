"""Progress processes exit after readiness; failures and no-tray fallback stay visible."""
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.desktop_launcher import STATUS_ENV, launch_desktop


class DesktopParentPipeSmoke(unittest.TestCase):
    def test_worker_exits_when_owning_launcher_closes_pipe(self):
        # Exercise an actual inherited stdin pipe; no app data or HTTP server.
        process = subprocess.Popen([sys.executable, '-c',
            'import time; from backend.desktop_launcher import watch_desktop_parent; '
            'watch_desktop_parent(); print("watching", flush=True); time.sleep(30)'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(process.stdout.readline().strip(), b'watching')
            self.assertIsNone(process.poll())
            process.stdin.close()
            self.assertNotEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            process.stdout.close(); process.stderr.close()


@unittest.skipUnless(sys.platform == 'win32', 'Windows desktop process creation')
class DesktopLauncherSmoke(unittest.TestCase):
    def test_windowless_worker_outlives_progress_process(self):
        with tempfile.TemporaryDirectory() as directory:
            def start(command, **options):
                self.assertIn('--desktop-worker', command)
                self.assertEqual(command[-3:], ['--data-dir', directory, '--desktop-worker'])
                self.assertEqual(options['creationflags'], 0x08000000)
                Path(options['env'][STATUS_ENV]).write_text('ready', encoding='utf-8')
                return process
            process = Mock()
            process.poll.return_value = None
            with patch('backend.desktop_launcher.subprocess.Popen', side_effect=start):
                self.assertTrue(launch_desktop(['--desktop', '--data-dir=old-data'],
                                              SimpleNamespace(tmp=Path(directory), root=Path(directory))))
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
                        self.assertFalse(launch_desktop(['--desktop'], SimpleNamespace(tmp=Path(directory), root=Path(directory))))
                    else:
                        with self.assertRaises(SystemExit) as result:
                            launch_desktop(['--desktop'], SimpleNamespace(tmp=Path(directory), root=Path(directory)))
                        self.assertEqual(result.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
