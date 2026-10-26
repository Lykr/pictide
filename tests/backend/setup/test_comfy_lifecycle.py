"""Real lightweight service processes verify lifecycle without ComfyUI, models or GPU requests."""
import asyncio
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from backend.host import APPLICATION, LOCAL_GENERATION, create_app, local_generation_access
from backend.paths import DataPaths
from backend.setup.comfy_discovery import discover, endpoint, layout, probe
from backend.setup.comfy_lifecycle import LocalComfyLifecycle
from backend.setup.comfy_process import ComfyProcess
from backend.setup.local_generation_session import read_state, write_state
from tests.backend.application.test_app import FakeBackend, configuration

SERVER = r'''
import argparse, json, pathlib, subprocess, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
parser = argparse.ArgumentParser()
parser.add_argument('--listen', default='127.0.0.1')
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--hang', action='store_true')
parser.add_argument('--exit', action='store_true')
parser.add_argument('--spawn-child')
args, _ = parser.parse_known_args()
if args.exit: sys.exit(3)
if args.spawn_child:
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    pathlib.Path(args.spawn_child).write_text(str(child.pid))
if args.hang: time.sleep(120)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = json.dumps({'system': {'comfyui_version': 'fixture', 'argv': sys.argv}, 'devices': []}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args): pass
HTTPServer((args.listen, args.port), Handler).serve_forever()
'''


def port():
    with socket.socket() as stream:
        stream.bind(('127.0.0.1', 0))
        return stream.getsockname()[1]


def alive(pid):
    if sys.platform == 'win32':
        import ctypes as c
        from ctypes import wintypes as w
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        kernel.CloseHandle.argtypes = [w.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        import os
        os.kill(pid, 0)
        status = Path(f'/proc/{pid}/stat')
        return not status.exists() or status.read_text().split()[2] != 'Z'
    except ProcessLookupError:
        return False


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='pictide-comfy-')
        self.addCleanup(self.temporary.cleanup)
        self.paths = DataPaths(Path(self.temporary.name) / 'data').ensure()
        self.install = Path(self.temporary.name) / 'Comfy UI 空格'
        self.install.mkdir()
        (self.install / 'main.py').write_text(SERVER, encoding='utf-8')
        self.config = dict(configuration(), id='local', api_key='', base_url=f'http://127.0.0.1:{port()}')
        self.service = self.fresh()
        self.addCleanup(self.service.close)
        self.payload = dict(enabled=True, backend_id='local', install_dir=str(self.install),
                            python=sys.executable, entry=str(self.install / 'main.py'), cwd=str(self.install), args=[])

    def fresh(self):
        return LocalComfyLifecycle(self.paths, lambda identifier: self.config if identifier == 'local' else None,
                                  lambda: [self.config])

    def external(self):
        _, host, number = endpoint(self.config)
        child = subprocess.Popen([sys.executable, str(self.install / 'main.py'), '--port', str(number)],
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.addCleanup(lambda: (child.terminate(), child.wait(timeout=5)) if child.poll() is None else None)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if probe(self.config['base_url']):
                return child
            time.sleep(.05)
        self.fail('fixture did not become ready')

    def test_save_does_not_start_and_session_owns_only_new_process_tree(self):
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(120)'],
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.addCleanup(lambda: (unrelated.terminate(), unrelated.wait(timeout=5)) if unrelated.poll() is None else None)
        child_file = self.install / 'child.pid'
        result = self.service.save(dict(self.payload, args=['--spawn-child', str(child_file)]))
        self.assertTrue(result['restart_required'] is False)  # The production host calls start before serving HTTP.
        self.assertIsNone(self.service.child)
        self.service.start()
        self.assertEqual(self.service.settings()['status']['phase'], 'running')
        first = self.service.child.process
        self.service.start()
        self.assertIs(self.service.child.process, first)
        pid = int(child_file.read_text())
        self.assertTrue(alive(pid))
        self.service.close()
        self.assertIsNotNone(first.poll())
        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertFalse(alive(pid))
        self.assertIsNone(unrelated.poll())
        self.assertIsNone(probe(self.config['base_url']))

    def test_running_external_service_is_reused_and_survives_exit(self):
        external = self.external()
        self.service.save(self.payload)
        with patch.object(ComfyProcess, 'launch', side_effect=AssertionError('must not spawn')):
            self.service.start()
        self.assertEqual(self.service.settings()['status']['phase'], 'external')
        self.assertFalse(self.service.settings()['status']['owned'])
        self.service.close()
        self.assertIsNone(external.poll())
        self.assertIsNotNone(probe(self.config['base_url']))

    def test_disabled_settings_and_explicit_changes_apply_on_next_start(self):
        self.service.start()
        self.assertEqual(self.service.settings()['status']['phase'], 'disabled')
        result = self.service.save(self.payload)
        self.assertTrue(result['restart_required'])
        self.assertIsNone(self.service.child)
        restarted = self.fresh()
        self.addCleanup(restarted.close)
        restarted.start()
        self.assertEqual(restarted.settings()['status']['phase'], 'running')
        result = restarted.save({'enabled': False})
        self.assertTrue(result['restart_required'])
        self.assertIsNone(restarted.child.process.poll())
        restarted.close()
        self.assertEqual(self.fresh().settings()['config']['enabled'], False)

    def test_bad_path_or_backend_is_rejected_but_disabling_remains_possible(self):
        for patch_value in ({'python': str(self.install / 'missing')}, {'entry': str(self.install / 'missing.py')},
                            {'backend_id': 'missing'}, {'args': 'not-an-array'}, {'enabled': 1}, {'cwd': 'missing'}):
            with self.subTest(value=patch_value), self.assertRaises(ValueError):
                self.service.save(dict(self.payload, **patch_value))
        self.service.save(self.payload)
        (self.install / 'main.py').unlink()
        self.assertFalse(self.service.save({'enabled': False})['config']['enabled'])
        self.assertIsNone(self.service.child)

    def test_launch_failure_or_timeout_keeps_pictide_available_and_reaps_child(self):
        for option in ('--exit', '--hang'):
            with self.subTest(option=option):
                service = self.fresh()
                service.save(dict(self.payload, args=[option]))
                original = ComfyProcess.launch
                def bounded(process, *args, **kwargs):
                    return original(process, *args, **kwargs, timeout=.3)
                with patch.object(ComfyProcess, 'launch', bounded):
                    service.start()
                result = service.settings()
                self.assertEqual(result['status']['phase'], 'failed')
                self.assertTrue(result['status']['error'])
                self.assertFalse(result['status']['owned'])
                self.assertIsNone(probe(self.config['base_url']))
                service.close()

    def test_shutdown_interrupts_startup_wait_and_reaps_process(self):
        self.service.save(dict(self.payload, args=['--hang']))
        worker = threading.Thread(target=self.service.start)
        worker.start()
        self.addCleanup(worker.join, 5)
        deadline = time.monotonic() + 5
        while (self.service.child is None or self.service.child.process is None) and time.monotonic() < deadline:
            time.sleep(.02)
        child = self.service.child.process
        self.service.close()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertIsNotNone(child.poll())
        self.assertIsNone(probe(self.config['base_url']))

    def test_occupied_non_comfy_port_is_not_spawned_over(self):
        self.service.save(self.payload)
        _, host, number = endpoint(self.config)
        with socket.socket() as listener:
            listener.bind((host, number))
            listener.listen()
            with patch.object(ComfyProcess, 'launch', side_effect=AssertionError('must not spawn')):
                self.service.start()
        self.assertEqual(self.service.settings()['status']['phase'], 'failed')
        self.assertFalse(self.service.settings()['status']['owned'])

    def test_corrupt_configuration_can_be_read_and_repaired(self):
        self.service.target.write_text('not json')
        self.service.start()
        self.assertEqual(self.service.settings()['status']['phase'], 'failed')
        result = self.service.save({'enabled': False})
        self.assertFalse(result['config']['enabled'])
        self.assertTrue(result['restart_required'])

    def test_legacy_managed_install_defaults_on_but_new_switch_can_disable_it(self):
        state = dict(mode='managed', backend_id='local', install_dir=str(self.paths.runtime / 'comfyui'),
                     profile_id='nvidia', recipe_id=None, configured=True)
        write_state(self.paths, state)
        external = self.external()
        with patch('backend.setup.comfy_lifecycle.ManagedComfy.start', side_effect=AssertionError('must reuse')):
            self.service.start()
        self.assertEqual(self.service.settings()['status']['phase'], 'external')
        self.assertTrue(self.service.settings()['config']['enabled'])
        self.service.close()
        self.assertIsNone(external.poll())
        self.service.save({'enabled': False})
        disabled = self.fresh()
        with patch('backend.setup.comfy_lifecycle.ManagedComfy.start', side_effect=AssertionError('must stay disabled')):
            disabled.start()
        self.assertEqual(disabled.settings()['status']['phase'], 'disabled')
        self.assertEqual(read_state(self.paths), state)

    def test_only_direct_loopback_comfy_endpoints_are_eligible(self):
        for value in ('http://192.168.0.3:8188', 'https://127.0.0.1:8188', 'http://127.0.0.1:8188/proxy',
                      'http://127.0.0.1:8188?query', 'http://user:password@127.0.0.1:8188'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                endpoint(dict(self.config, base_url=value))
        self.assertEqual(endpoint(dict(self.config, base_url='http://localhost:8188'))[1:], ('127.0.0.1', 8188))

    def test_desktop_discovery_keeps_models_io_python_and_arguments_without_mutation(self):
        appdata = Path(self.temporary.name) / 'desktop'
        directory = appdata / 'Comfy Desktop'
        directory.mkdir(parents=True)
        python = self.install / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        python.parent.mkdir(parents=True)
        python.write_text('fixture')
        records = json.dumps([dict(id='installation', installPath=str(self.install), launchArgs='--cpu --listen 0.0.0.0')])
        (directory / 'installations.json').write_text(records)
        (directory / 'settings.json').write_text(json.dumps({'inputDir': str(self.install / 'input'), 'outputDir': str(self.install / 'output')}))
        models = directory / 'instance-model-paths' / 'installation.yaml'
        models.parent.mkdir()
        models.write_text('fixture')
        with patch('backend.setup.comfy_discovery.desktop_roots', return_value=[directory]), patch('backend.setup.comfy_discovery.probe', return_value=None):
            result = discover(self.paths, self.config)
        candidate = next(item for item in result['candidates'] if item['source'] == 'desktop')
        self.assertEqual(candidate['python'], str(python))
        self.assertIn(str(models), candidate['args'])
        self.assertIn('--cpu', candidate['args'])
        self.assertIn(str(self.install / 'output'), candidate['args'])
        self.assertEqual((directory / 'installations.json').read_text(), records)
        self.assertIsNone(self.service.child)

    def test_running_absolute_entry_and_virtual_environment_are_discovered(self):
        python = self.install / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        python.parent.mkdir(parents=True)
        python.write_text('fixture')
        stats = {'system': {'argv': [str(self.install / 'main.py'), '--cpu']}}
        with patch('backend.setup.comfy_discovery.desktop_roots', return_value=[]), patch('backend.setup.comfy_discovery.probe', return_value=stats):
            result = discover(self.paths, self.config)
        item = next(item for item in result['candidates'] if item['entry'] == str(self.install / 'main.py'))
        self.assertEqual(item['args'], ['--cpu'])
        self.assertEqual(item['cwd'], str(self.install))


class LifecycleHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_settings_never_spawn_and_first_bootstrap_survives_startup_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = DataPaths(temporary).ensure()
            paths.runtime.joinpath('comfyui-lifecycle.json').write_text(json.dumps(dict(enabled=True, backend_id='missing',
                install_dir='missing', python='', entry='', cwd='', args=[])))
            fake = FakeBackend()
            app = create_app(paths.root, lambda config, session: fake)
            async with TestClient(TestServer(app)) as client:
                self.assertEqual((await client.get('/api/bootstrap')).status, 200)
                response = await client.get('/api/settings/local-generation')
                status = await response.json()
                self.assertTrue(status['can_configure'])
                self.assertEqual(status['status']['phase'], 'failed')
                response = await client.put('/api/settings/local-generation', json={'enabled': False})
                self.assertEqual(response.status, 200)
                self.assertTrue((await response.json())['restart_required'])
                self.assertFalse(fake.submissions)
                response = await client.post('/api/settings/local-generation/detect', json={'backend_id': 'missing'})
                self.assertEqual(response.status, 400)
                self.assertNotIn('api_key', await (await client.get('/api/settings/local-generation')).text())

    async def test_saved_configuration_starts_only_after_host_restart_and_closes_on_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = DataPaths(temporary).ensure()
            install = Path(temporary) / 'existing ComfyUI'
            install.mkdir()
            (install / 'main.py').write_text(SERVER, encoding='utf-8')
            config = dict(configuration(), id='local', api_key='', base_url=f'http://127.0.0.1:{port()}')
            fake = FakeBackend()
            app = create_app(paths.root, lambda config, session: fake)
            app[APPLICATION].storage.save_backend(config)
            async with TestClient(TestServer(app)) as client:
                payload = dict(enabled=True, backend_id='local', install_dir=str(install), python=sys.executable,
                               entry=str(install / 'main.py'), cwd=str(install), args=[])
                response = await client.put('/api/settings/local-generation', json=payload)
                self.assertEqual(response.status, 200, await response.text())
                self.assertTrue((await response.json())['restart_required'])
                self.assertIsNone(await asyncio.to_thread(probe, config['base_url']))
            restarted = create_app(paths.root, lambda config, session: fake)
            async with TestClient(TestServer(restarted)) as client:
                self.assertEqual((await client.get('/api/bootstrap')).status, 200)
                state = await (await client.get('/api/settings/local-generation')).json()
                self.assertEqual(state['status']['phase'], 'running')
                self.assertTrue(state['status']['owned'])
                self.assertFalse(fake.submissions)
            self.assertIsNone(await asyncio.to_thread(probe, config['base_url']))

    async def test_loopback_guard_requires_both_local_peer_and_localhost_address(self):
        from types import SimpleNamespace
        self.assertTrue(local_generation_access(SimpleNamespace(remote='127.0.0.1', host='localhost:8189')))
        for peer, host in [('192.168.1.2', 'localhost:8189'), ('127.0.0.1', '192.168.1.2:8189')]:
            self.assertFalse(local_generation_access(SimpleNamespace(remote=peer, host=host)))
        with tempfile.TemporaryDirectory() as temporary:
            app = create_app(temporary, lambda config, session: FakeBackend())
            with patch('backend.host.local_generation_access', return_value=False):
                async with TestClient(TestServer(app)) as client:
                    response = await client.get('/api/settings/local-generation')
                    self.assertEqual(await response.json(), {'can_configure': False})
                    for path in ('/api/settings/local-generation', '/api/settings/local-generation/detect'):
                        response = await (client.put(path, json={'enabled': True}) if path.endswith('generation') else client.post(path, json={}))
                        self.assertEqual(response.status, 403)


if __name__ == '__main__':
    unittest.main()
