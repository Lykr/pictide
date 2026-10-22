"""Progress processes exit after readiness; failures and no-tray fallback stay visible."""
import os
import asyncio
import socket
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.desktop.launcher import STATUS_ENV, launch_desktop, reserve_desktop_socket
from backend import host


class DesktopSocketSmoke(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'Unix address reuse and TIME_WAIT behavior')
    def test_unix_desktop_can_restart_after_active_connection_and_rejects_another_owner(self):
        with reserve_desktop_socket('127.0.0.1', 0) as server:
            port = server.getsockname()[1]
            with self.assertRaises(OSError):
                reserve_desktop_socket('127.0.0.1', port)
            with socket.create_connection(('127.0.0.1', port), timeout=2) as client:
                connection, _ = server.accept()
                connection.close()
                self.assertEqual(client.recv(1), b'')
        with reserve_desktop_socket('127.0.0.1', port) as restarted:
            self.assertEqual(restarted.getsockname()[1], port)

    def test_reserved_address_cannot_be_owned_by_another_service(self):
        with reserve_desktop_socket('127.0.0.1', 0) as server:
            port = server.getsockname()[1]
            with self.assertRaises(OSError):
                reserve_desktop_socket('127.0.0.1', port)

    def test_macos_worker_rejects_busy_port_before_preparing_dependencies(self):
        with tempfile.TemporaryDirectory() as directory, reserve_desktop_socket('127.0.0.1', 0) as occupied:
            paths = SimpleNamespace(root=Path(directory), configure_runtime=Mock())
            with patch('backend.host.sys.platform', 'darwin'), patch('backend.host.sys.stdout', Mock()), \
                    patch('backend.host.sys.stderr', Mock()), patch('backend.host.DataPaths', return_value=paths), \
                    patch('backend.host.PictideApplication.prepare_startup') as prepare, \
                    patch('backend.host.create_app') as create, patch('backend.host.logging.getLogger', return_value=Mock()):
                with self.assertRaises(SystemExit) as raised:
                    host.main(['--desktop-worker', '--cli', '--no-browser', '--port', str(occupied.getsockname()[1])])
            self.assertEqual(raised.exception.code, 1)
            prepare.assert_not_called()
            create.assert_not_called()

    def test_macos_worker_reports_ready_only_after_application_startup_and_closes_socket(self):
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / 'worker.status'
            paths = SimpleNamespace(root=Path(directory), tmp=Path(directory), configure_runtime=Mock())
            app = host.web.Application()
            app[host.APPLICATION] = SimpleNamespace(updates=SimpleNamespace(installation=None))
            owned = []
            def prepare(*args):
                self.assertFalse(status.exists())
            def serve(application, **options):
                self.assertIs(application, app)
                server = options['sock']
                owned.append(server)
                with self.assertRaises(OSError):
                    reserve_desktop_socket('127.0.0.1', server.getsockname()[1])
                for callback in app.on_startup:
                    asyncio.run(callback(app))
                self.assertEqual(status.read_text(), 'ready')
            with patch('backend.host.sys.platform', 'darwin'), patch('backend.host.sys.stdout', Mock()), \
                    patch('backend.host.sys.stderr', Mock()), patch('backend.host.DataPaths', return_value=paths), \
                    patch('backend.host.PictideApplication.prepare_startup', side_effect=prepare), \
                    patch('backend.host.create_app', return_value=app), \
                    patch('backend.host.web.run_app', side_effect=serve), patch.dict(os.environ, {STATUS_ENV: str(status)}):
                host.main(['--desktop-worker', '--cli', '--no-browser', '--port', '0'])
            self.assertEqual(len(owned), 1)
            self.assertEqual(owned[0].fileno(), -1)


class DesktopParentPipeSmoke(unittest.TestCase):
    def test_worker_can_exit_cleanly_while_parent_keeps_pipe_open(self):
        process = subprocess.Popen([sys.executable, '-c',
            'import time; from backend.desktop.launcher import watch_desktop_parent; '
            'watch_desktop_parent(); print("watching", flush=True); time.sleep(0.2)'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(process.stdout.readline().strip(), b'watching')
            self.assertEqual(process.wait(timeout=5), 0, process.stderr.read().decode())
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            process.stdin.close(); process.stdout.close(); process.stderr.close()

    def test_worker_exits_when_owning_launcher_closes_pipe(self):
        # Exercise an actual inherited stdin pipe; no app data or HTTP server.
        process = subprocess.Popen([sys.executable, '-c',
            'import time; from backend.desktop.launcher import watch_desktop_parent; '
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
            with patch('backend.desktop.launcher.subprocess.Popen', side_effect=start), \
                    patch('backend.desktop.launcher.read_startup_output', return_value=b''):
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
                with patch('backend.desktop.launcher.subprocess.Popen', side_effect=start), \
                        patch('backend.desktop.launcher.read_startup_output', return_value=b''), \
                        patch('backend.desktop.launcher.sys.stdin', None):
                    if status == 'console':
                        self.assertFalse(launch_desktop(['--desktop'], SimpleNamespace(tmp=Path(directory), root=Path(directory))))
                    else:
                        with self.assertRaises(SystemExit) as result:
                            launch_desktop(['--desktop'], SimpleNamespace(tmp=Path(directory), root=Path(directory)))
                        self.assertEqual(result.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
