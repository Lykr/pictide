"""Real process exceptions, startup handoff, privacy and bounded retention."""
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from backend.runtime_logging import make_log_handler, trim_startup_logs


class RuntimeLoggingSmoke(unittest.TestCase):
    def test_dependency_failure_is_visible_before_http_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            code = '''from backend import host
def fail(*args): raise RuntimeError('MiniLM download failed: certificate verify failed')
host.PictideApplication.prepare_startup=fail
host.main(['--cli','--no-browser','--port','0'])
'''
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, timeout=15,
                                    env=dict(os.environ, PICTIDE_DATA_DIR=directory, PYTHONIOENCODING='utf-8'))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b'MiniLM', result.stderr)
            text = (Path(directory) / 'logs/pictide.log').read_text(encoding='utf-8')
            for message in ('Starting Pictide version=', 'data_directory=', 'Traceback',
                            'MiniLM download failed: certificate verify failed', 'Pictide stopped'):
                self.assertIn(message, text)
            self.assertFalse((Path(directory) / 'db/pictide.sqlite3').exists())

    def test_formatter_retains_traceback_without_prompt_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'pictide.log'
            logger = logging.Logger('private-test', logging.INFO)
            handler = make_log_handler(target)
            logger.addHandler(handler)
            try:
                try:
                    raise ValueError('server echoed a private prompt, api_key="key-value"; Authorization: Bearer bearer-value; '
                                     'https://username:password@example.test/image?token=url-value')
                except ValueError:
                    logger.exception('Generation failed job_id=test backend_id=local',
                                     extra={'sensitive_values': ('a private prompt',)})
                text = target.read_text(encoding='utf-8')
                self.assertIn('Traceback', text)
                self.assertIn('ValueError', text)
                self.assertIn('job_id=test backend_id=local', text)
                self.assertIn(f'pid={os.getpid()}', text)
                # Traceback source lines can contain test literals too; mask all
                # known private text in both the exception and its source line.
                for value in ('a private prompt', 'key-value', 'bearer-value', 'username:password', 'url-value'):
                    self.assertNotIn(value, text)
            finally:
                handler.close()

    def test_thread_loop_and_unhandled_main_errors_reach_the_same_file(self):
        with tempfile.TemporaryDirectory() as directory:
            code = '''import asyncio,logging,threading
from backend.paths import DataPaths
from backend.runtime_logging import capture_exceptions
DataPaths().configure_runtime()
previous=threading.excepthook
sources=[logging.getLogger(n) for n in ('asyncio','aiohttp.server')]
before=[list(s.handlers) for s in sources]
def fail(): raise RuntimeError('thread-failure')
try:
 with capture_exceptions():
  thread=threading.Thread(target=fail,name='owned-test-thread');thread.start();thread.join()
  loop=asyncio.new_event_loop()
  loop.call_exception_handler({'message':'loop-failure','exception':ValueError('async-failure')})
  loop.close()
  logging.getLogger('aiohttp.server').error('server-failure')
  raise LookupError('main-failure')
except LookupError: pass
assert threading.excepthook is previous
assert all(list(s.handlers)==old for s,old in zip(sources,before))
print('console intact',flush=True)
'''
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, timeout=15,
                                    env=dict(os.environ, PICTIDE_DATA_DIR=directory))
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertIn(b'console intact', result.stdout)
            text = (Path(directory) / 'logs/pictide.log').read_text(encoding='utf-8')
            for message in ('Unhandled thread exception', 'thread-failure', 'loop-failure', 'async-failure',
                            'server-failure', 'Unhandled application exception', 'main-failure'):
                self.assertIn(message, text)
            self.assertEqual(text.count('Unhandled thread exception'), 1)
            self.assertEqual(text.count('Unhandled application exception'), 1)
            self.assertFalse((Path(directory) / 'logs/comfyui.log').exists())

    def test_ready_worker_silences_raw_output_while_logs_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture, status = root / 'capture.log', root / 'ready.status'
            code = '''import logging,sys
from backend.paths import DataPaths
from backend.desktop.launcher import notify_launcher
DataPaths().configure_runtime()
print('preparing dependency',flush=True)
notify_launcher('ready')
print('must not reach startup pipe',flush=True)
logging.getLogger('backend').info('runtime event after handoff')
sys.stdin.buffer.read(1)
'''
            process = subprocess.Popen([sys.executable, '-u', '-c', code], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=dict(os.environ, PICTIDE_DATA_DIR=str(root / 'data'), PICTIDE_DESKTOP_STATUS=str(status)))
            try:
                capture.write_bytes(process.stdout.readline())
                deadline = time.monotonic() + 10
                while not status.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertEqual(status.read_text(), 'ready')
                self.assertIsNone(process.poll())
                self.assertIn('preparing dependency', capture.read_text())
                capture.unlink()  # Only the parent owns capture files; a venv shim cannot lock them.
                process.stdin.write(b'x'); process.stdin.close()
                self.assertEqual(process.wait(timeout=5), 0)
                self.assertEqual(process.stdout.read(), b'')
                text = (root / 'data/logs/pictide.log').read_text(encoding='utf-8')
                self.assertIn('runtime event after handoff', text)
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=5)
                if not process.stdin.closed:
                    process.stdin.close()
                process.stdout.close()

    def test_new_startup_fallbacks_are_bounded_and_old_material_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = root / 'desktop-startup-old.log'
            historical.write_text('old diagnostic')
            for number in range(6):
                path = root / f'desktop-output-{number}.log'
                path.write_text('failure')
                os.utime(path, (number + 1, number + 1))
            trim_startup_logs(root)
            self.assertEqual(sorted(path.name for path in root.glob('desktop-output-*.log')),
                             [f'desktop-output-{number}.log' for number in range(3, 6)])
            self.assertEqual(historical.read_text(), 'old diagnostic')


if __name__ == '__main__':
    unittest.main()
