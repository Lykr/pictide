"""Owned subprocess output stays bounded and closes with its ComfyUI session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.local_generation_session import ManagedComfy, _ManagedOutput
from backend.paths import DataPaths


class ManagedOutputSmoke(unittest.TestCase):
    def test_long_output_rotates_and_drains_both_streams_before_close(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = DataPaths(directory).ensure()
            managed = ManagedComfy(paths, {})
            child = subprocess.Popen([
                sys.executable, '-u', '-c',
                "import sys; sys.stdout.write('x' * (5 * 1024 * 1024)); "
                "sys.stdout.write('\\nfinal stdout \\u4e2d\\u6587\\n'); "
                "sys.stderr.write('final stderr\\n')",
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=dict(os.environ, PYTHONIOENCODING='utf-8'))
            output = _ManagedOutput(child.stdout, paths.logs / 'comfyui.log')
            managed.process, managed.output = child, output
            try:
                self.assertEqual(child.wait(timeout=15), 0)
                with self.assertLogs('backend.local_generation', level='INFO') as events:
                    managed.close()
                self.assertIn(f'pid={child.pid}', '\n'.join(events.output))
                self.assertIn('exit_code=0', '\n'.join(events.output))
                self.assertFalse(output.thread.is_alive())
                self.assertTrue(child.stdout.closed)
                self.assertIsNone(output.handler.stream)
                self.assertEqual(output.logger.handlers, [])
                files = list(paths.logs.glob('comfyui.log*'))
                self.assertEqual(len(files), 4)
                self.assertTrue(all(path.stat().st_size <= 1024 * 1024 for path in files))
                tail = (paths.logs / 'comfyui.log').read_text(encoding='utf-8')[-2000:]
                self.assertIn('final stdout 中文', tail)
                self.assertIn('final stderr', tail)
                managed.close()
            finally:
                managed.close()

    def test_managed_start_reports_readiness_and_releases_owned_output(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = DataPaths(directory).ensure()
            install = paths.runtime / 'comfyui'
            for relative in ('python_embeded/python.exe', 'ComfyUI/main.py'):
                target = install / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            # Only this tiny HTTP fixture runs; no ComfyUI or GPU is started.
            script = Path(directory) / 'fake_service.py'
            script.write_text(
                "import json, sys\n"
                "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                "class Handler(BaseHTTPRequestHandler):\n"
                " def do_GET(self):\n"
                "  data = json.dumps({'system': {}}).encode()\n"
                "  self.send_response(200); self.end_headers(); self.wfile.write(data)\n"
                " def log_message(self, *args): pass\n"
                "print('fixture stdout', flush=True)\n"
                "print('fixture stderr', file=sys.stderr, flush=True)\n"
                "HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()\n",
                encoding='utf-8',
            )
            managed = ManagedComfy(paths, {'install_dir': str(install), 'profile_id': 'cpu'})
            real_popen = subprocess.Popen
            captured = {}

            def fake_service(command, **kwargs):
                captured.update(kwargs)
                port = command[command.index('--port') + 1]
                return real_popen([sys.executable, '-u', str(script), port], **kwargs)

            try:
                with patch('backend.local_generation_session.subprocess.Popen', side_effect=fake_service):
                    with self.assertLogs('backend.local_generation', level='INFO') as events:
                        address = managed.start()
                child, output = managed.process, managed.output
                self.assertTrue(address.startswith('http://127.0.0.1:'))
                self.assertIn('Managed ComfyUI started', '\n'.join(events.output))
                self.assertIn('Managed ComfyUI ready', '\n'.join(events.output))
                self.assertEqual(captured['stdout'], subprocess.PIPE)
                self.assertEqual(captured['stderr'], subprocess.STDOUT)
                self.assertEqual(captured['env']['PYTHONIOENCODING'], 'utf-8')
                state = json.loads((paths.runtime / 'local-generation.json').read_text(encoding='utf-8'))
                self.assertEqual(state['port'], int(address.rsplit(':', 1)[1]))
                managed.close()
                self.assertIsNotNone(child.returncode)
                self.assertFalse(output.thread.is_alive())
                text = (paths.logs / 'comfyui.log').read_text(encoding='utf-8')
                self.assertIn('fixture stdout', text)
                self.assertIn('fixture stderr', text)
            finally:
                managed.close()

    def test_no_process_means_no_comfyui_log(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = DataPaths(directory).ensure()
            ManagedComfy(paths, {}).close()
            self.assertFalse((paths.logs / 'comfyui.log').exists())


if __name__ == '__main__':
    unittest.main()
