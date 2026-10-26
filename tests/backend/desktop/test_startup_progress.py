"""Indeterminate startup feedback stays truthful, bounded and safe in real console handoff."""
import io
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.desktop.startup_progress import ANIMATION_ENV, COLUMNS_ENV, StartupProgress, _width
from backend.desktop.launcher import STATUS_ENV, launch_desktop


class StartupProgressTests(unittest.TestCase):
    def test_waiting_animation_has_elapsed_time_bounded_chinese_width_and_no_percentage(self):
        stream, current = io.StringIO(), [0.0]
        with patch.dict(os.environ, {ANIMATION_ENV: '1', COLUMNS_ENV: '60'}), \
             patch('backend.desktop.text.system_language', return_value='zh-CN'):
            view = StartupProgress('data/logs/comfyui.log', stream=stream, clock=lambda: current[0])
            view.start()
            before = stream.getvalue()
            current[0] = .25
            view.tick('正在初始化运行环境')
            self.assertNotEqual(stream.getvalue(), before)
            current[0] = 12
            view.tick('正在加载自定义节点' * 50)
            self.assertIn('00:12', stream.getvalue())
            self.assertNotIn('ComfyUI 已就绪', stream.getvalue())
            view.finish('ready')
            self.assertIn('ComfyUI 已就绪 · 用时 00:12', stream.getvalue())
            for line in stream.getvalue().split('\r')[1:]:
                if '\n' not in line:
                    self.assertLessEqual(_width(line), 59)
            self.assertNotIn('%', stream.getvalue())
            self.assertNotIn('\x1b', stream.getvalue())
            finished = stream.getvalue()
            view.tick('late output'); view.finish('failed')
            self.assertEqual(stream.getvalue(), finished)

    def test_redirected_output_is_plain_throttled_and_keeps_log_context_on_failure(self):
        stream, current = io.StringIO(), [0.0]
        with patch.dict(os.environ, {ANIMATION_ENV: '0'}), \
             patch('backend.desktop.text.system_language', return_value='en'):
            view = StartupProgress('data/logs/comfyui.log', stream=stream, clock=lambda: current[0])
            view.start()
            before = stream.getvalue()
            current[0] = 1
            view.tick('not ready')
            self.assertEqual(stream.getvalue(), before)
            current[0] = 5
            view.tick('\x1b[31mImporting nodes token=private-token\x1b[0m\x07')
            view.finish('failed')
            text = stream.getvalue()
            self.assertIn('Startup log: data/logs/comfyui.log', text)
            self.assertIn('00:05', text)
            self.assertIn('Importing nodes token=[redacted]', text)
            self.assertIn('ComfyUI startup failed', text)
            self.assertNotIn('private-token', text)
            self.assertNotIn('ComfyUI is ready', text)
            for control in ('\r', '\x1b', '\x07'):
                self.assertNotIn(control, text)

    def test_cancelled_or_broken_output_never_reports_ready_or_interrupts_startup(self):
        with patch.dict(os.environ, {ANIMATION_ENV: '0'}), \
             patch('backend.desktop.text.system_language', return_value='en'):
            stream = io.StringIO()
            view = StartupProgress('comfyui.log', stream=stream)
            view.start(); view.finish('cancelled')
            self.assertIn('ComfyUI startup cancelled', stream.getvalue())
            self.assertNotIn('ComfyUI is ready', stream.getvalue())
            broken = Mock()
            broken.isatty.return_value = False
            broken.write.side_effect = OSError('terminal closed')
            view = StartupProgress('comfyui.log', stream=broken)
            view.start(); view.tick('loading'); view.finish('ready')
            self.assertIsNone(view.stream)

    @unittest.skipUnless(os.name == 'nt', 'Windows hidden worker output handoff')
    def test_real_windowless_worker_relays_animation_and_survives_ready_handoff(self):
        worker_code = r"""
import pathlib, socket, sys, time
from backend.paths import DataPaths
from backend.desktop import text
from backend.desktop.launcher import notify_launcher
from backend.setup.comfy_process import ComfyProcess
from tests.backend.setup.test_comfy_lifecycle import SERVER
text.system_language = lambda: 'en'
paths = DataPaths(sys.argv[1]).ensure()
script = paths.tmp / 'main.py'
script.write_text(SERVER.replace('if args.hang: time.sleep(120)',
    "print('Loading custom nodes', flush=True); time.sleep(.8)\nif args.hang: time.sleep(120)"), encoding='utf-8')
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
owned = ComfyProcess(paths)
try:
    owned.launch([sys.executable, '-u', str(script), '--port', str(port)], paths.tmp, f'http://127.0.0.1:{port}')
    notify_launcher('ready')
    while not (paths.tmp / 'stop').exists(): time.sleep(.05)
finally:
    owned.close()
"""
        class Terminal(io.StringIO):
            def isatty(self): return True
        with tempfile.TemporaryDirectory() as directory:
            paths = type('Paths', (), {'root': Path(directory), 'tmp': Path(directory) / 'tmp'})()
            paths.tmp.mkdir()
            stream, children = Terminal(), []
            real_popen = subprocess.Popen
            def launch(command, **options):
                child = real_popen([sys.executable, '-u', '-c', worker_code, directory], **options)
                children.append(child)
                return child
            try:
                with patch('backend.desktop.launcher.subprocess.Popen', side_effect=launch), \
                     patch('backend.desktop.launcher.sys.stdout', stream):
                    self.assertTrue(launch_desktop(['--desktop'], paths))
                output = stream.getvalue()
                self.assertIn('Waiting for ComfyUI', output)
                self.assertIn('Loading custom nodes', output)
                self.assertIn('ComfyUI is ready', output)
                self.assertIn('\r', output)
                self.assertIsNone(children[0].poll())
                self.assertFalse(list(paths.tmp.glob('desktop-startup-*.status')))
                self.assertFalse(list(paths.tmp.glob('desktop-output-*.log')))
                (paths.tmp / 'stop').touch()
                self.assertEqual(children[0].wait(timeout=10), 0)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.terminate(); child.wait(timeout=5)

    @unittest.skipUnless(os.name == 'nt', 'Windows hidden worker output handoff')
    def test_launcher_passes_actual_terminal_capability_without_changing_parent_environment(self):
        for interactive in (False, True):
            with self.subTest(interactive=interactive), tempfile.TemporaryDirectory() as directory:
                process, captured = Mock(), {}
                process.poll.return_value = None
                def start(command, **options):
                    captured.update(options['env'])
                    Path(options['env'][STATUS_ENV]).write_text('ready', encoding='utf-8')
                    return process
                stdout = Mock()
                stdout.isatty.return_value = interactive
                original = os.environ.get(ANIMATION_ENV)
                with patch('backend.desktop.launcher.subprocess.Popen', side_effect=start), \
                     patch('backend.desktop.launcher.read_startup_output', return_value=b''), \
                     patch('backend.desktop.launcher.sys.stdout', stdout):
                    self.assertTrue(launch_desktop(['--desktop'], type('Paths', (), {'root': Path(directory), 'tmp': Path(directory)})()))
                self.assertEqual(captured[ANIMATION_ENV], '1' if interactive else '0')
                self.assertGreater(int(captured[COLUMNS_ENV]), 0)
                self.assertEqual(os.environ.get(ANIMATION_ENV), original)
                process.terminate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
