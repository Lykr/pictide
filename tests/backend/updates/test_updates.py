import asyncio
from contextlib import redirect_stdout, redirect_stderr, contextmanager, closing
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
import zipfile

from aiohttp.test_utils import TestClient, TestServer
from backend import host
from backend.paths import DataPaths
from backend.store.update_state import unfinished_jobs
from backend.updates.apply import apply_plan, create_plan, restart
from backend.updates.contracts import Installation, Release, PROGRAM_FILES
from backend.updates.installation import extract_package, install_reason
from backend.updates.releases import API, PAGE, read_release
from backend.updates.service import UpdateService
from backend.updates.lock import UpdateLease


class RestartModeTests(unittest.TestCase):
    def test_restart_preserves_desktop_cli_and_network_arguments(self):
        cases = (
            ('darwin', 'Pictide.app/Contents/MacOS/Pictide', []),
            ('darwin', 'Pictide.app/Contents/MacOS/Pictide', ['--cli', '--no-browser']),
            ('win32', 'Pictide.exe', ['--desktop']),
            ('win32', 'Pictide.exe', ['--cli', '--no-browser']),
            ('linux', 'data/runtime/pictide/Pictide', ['--cli', '--no-browser']),
        )
        with tempfile.TemporaryDirectory() as directory:
            for platform, program, mode in cases:
                with self.subTest(platform=platform, mode=mode):
                    arguments = [*mode, '--lan', '--port', '8197', '--data-dir', str(Path(directory) / 'personal data')]
                    installation = Installation(directory, platform, 'test', '0.6.1')
                    plan = dict(restart_args=arguments, pids=[123, 456])
                    with patch('backend.updates.apply.subprocess.Popen') as launch:
                        restart(plan, installation)
                    self.assertEqual(launch.call_args.args[0], [str(Path(directory) / program), *arguments])
                    self.assertEqual(plan['restart_args'], arguments)


def package_files(package, label, version='0.5.1'):
    package.mkdir(parents=True, exist_ok=True)
    for name in PROGRAM_FILES['win32']:
        path = package / name
        if name in ('_internal', 'licenses'):
            path.mkdir(exist_ok=True)
        else:
            path.write_text(label, encoding='utf8')
    metadata = package / '_internal/resources/installation.json'
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps(dict(schema=1, version=version, platform='win32', arch='amd64')), encoding='utf8')
    (package / 'licenses/fixture.txt').write_text('Fixture license', encoding='utf8')


@contextmanager
def open_database(path):
    with closing(sqlite3.connect(path)) as connection, connection:
        yield connection


def fixture(root):
    install = root / 'application'
    package_files(install, 'previous', '0.5.0')
    paths = DataPaths(install / 'data').ensure()
    package = paths.cache / 'updates/0.5.1/unpacked/Pictide'
    package_files(package, 'updated')
    installation = Installation(str(install), 'win32', 'amd64', '0.5.0')
    release = Release('0.5.1', PAGE + '/tag/v0.5.1', True, '', {})
    service = UpdateService(paths, installation=installation)
    service.release, service.package = release, package
    service.state.update(phase='ready', compatible=True, latest_version=release.version)
    return paths, installation, service


class ReleaseTests(unittest.TestCase):
    def test_operations_are_serialized_and_other_instances_block_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, installation, service = fixture(Path(directory))
            with UpdateLease(paths.root), self.assertRaises(ValueError):
                UpdateLease(paths.root)
            with patch('backend.updates.apply.running_pids', return_value={987654}), self.assertRaisesRegex(ValueError, 'other instances'):
                create_plan(service, ['--cli'], [])

    def test_explicit_compatibility_and_asset_binding(self):
        url = PAGE + '/download/v0.5.1/'
        name = 'pictide-0.5.1-win32-amd64.zip'
        document = dict(tag_name='v0.5.1', draft=False, prerelease=False, assets=[
            dict(name='update.json', browser_download_url=url + 'update.json'),
            dict(name=name, browser_download_url=url + name, size=10)])
        manifest = dict(schema=1, version='0.5.1', direct_upgrade_from=dict(minimum='0.5.0', maximum_exclusive='0.5.1'),
                        assets={'win32-amd64': dict(name=name, bytes=10, unpacked_bytes=100, sha256='a' * 64, install_verified=True)})
        requests = []
        def opener(request, **kwargs):
            requests.append(request.full_url)
            return io.BytesIO(json.dumps(document if request.full_url == API else manifest).encode())
        self.assertTrue(read_release('0.5.0', 'win32', 'amd64', opener=opener).compatible)
        self.assertEqual(requests, [API, url + 'update.json'])
        self.assertEqual(read_release('0.4.9', 'win32', 'amd64', opener=opener).reason, 'incompatible')
        manifest['assets']['win32-amd64']['install_verified'] = False
        self.assertEqual(read_release('0.5.0', 'win32', 'amd64', opener=opener).reason, 'platform_unverified')
        manifest['assets']['win32-amd64']['install_verified'] = True
        document['assets'][1]['browser_download_url'] = 'https://example.invalid/other.zip'
        with self.assertRaises(ValueError):
            read_release('0.5.0', 'win32', 'amd64', opener=opener)
        document['assets'] = []
        self.assertEqual(read_release('0.5.0', 'win32', 'amd64', opener=opener).reason, 'manual_update')

    def test_upgrade_backs_up_data_and_runtime_failure_restores_only_program(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                paths, installation, service = fixture(Path(directory))
                for relative in ('images/liked.png', 'models/user-model.bin', 'libraries/custom.sqlite3'):
                    target = paths.root / relative
                    target.parent.mkdir(exist_ok=True, parents=True)
                    target.write_bytes(b'personal')
                (Path(installation.root) / 'pictide.local.json').write_text('user settings')
                with open_database(paths.database) as database:
                    database.execute('CREATE TABLE evidence(value TEXT)')
                    database.execute("INSERT INTO evidence VALUES ('old')")
                plan, helper = create_plan(service, ['--cli'], [])
                self.assertEqual(helper, service.package / 'Pictide.exe')
                self.assertFalse((plan.parent / 'helper').exists())
                def check(installed):
                    self.assertEqual((Path(installed.root) / 'Pictide.exe').read_text(), 'updated')
                    if fail:
                        # Program rollback must leave any later database writes intact.
                        with open_database(paths.database) as database:
                            database.execute("UPDATE evidence SET value='new'")
                        with open_database(paths.root / 'db/new.sqlite3') as database:
                            database.execute('CREATE TABLE later_write(value TEXT)')
                        raise RuntimeError('Simulated runtime load failure')
                restart = Mock()
                if fail:
                    with self.assertRaisesRegex(RuntimeError, 'Simulated runtime load failure'):
                        apply_plan(plan, checker=check, restarter=restart)
                else:
                    apply_plan(plan, checker=check, restarter=restart)
                self.assertEqual((Path(installation.root) / 'Pictide.exe').read_text(), 'previous' if fail else 'updated')
                with open_database(paths.database) as database:
                    self.assertEqual(database.execute('SELECT value FROM evidence').fetchone()[0], 'new' if fail else 'old')
                result = json.loads((paths.tmp / 'updates/result.json').read_text(encoding='utf8'))
                with open_database(Path(result['backup']) / 'db' / paths.database.name) as database:
                    self.assertEqual(database.execute('SELECT value FROM evidence').fetchone()[0], 'old')
                if fail:
                    self.assertTrue((paths.root / 'db/new.sqlite3').exists())
                self.assertEqual((paths.images / 'liked.png').read_bytes(), b'personal')
                self.assertEqual((paths.models / 'user-model.bin').read_bytes(), b'personal')
                self.assertEqual((paths.libraries / 'custom.sqlite3').read_bytes(), b'personal')
                self.assertEqual((Path(installation.root) / 'pictide.local.json').read_text(), 'user settings')
                restart.assert_called_once()

    def test_partial_file_replacement_failure_restores_the_previous_program(self):
        from backend.updates.apply import copy
        with tempfile.TemporaryDirectory() as directory:
            paths, installation, service = fixture(Path(directory))
            plan, _ = create_plan(service, ['--cli'], [])
            def failing_copy(source, target):
                if source == service.package / '_internal':
                    raise OSError('Simulated file replacement failure')
                return copy(source, target)
            checker, restart = Mock(), Mock()
            with patch('backend.updates.apply.copy', side_effect=failing_copy):
                with self.assertRaisesRegex(OSError, 'file replacement failure'):
                    apply_plan(plan, checker=checker, restarter=restart)
            self.assertEqual((Path(installation.root) / 'Pictide.exe').read_text(), 'previous')
            self.assertEqual(json.loads((Path(installation.root) / '_internal/resources/installation.json').read_text())['version'], '0.5.0')
            checker.assert_not_called()
            restart.assert_called_once()

    def test_process_launch_failure_restores_program_and_retries_the_previous_version(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, installation, service = fixture(Path(directory))
            plan, _ = create_plan(service, ['--cli'], [])
            restart = Mock(side_effect=[OSError('Cannot launch the updated program'), None])
            with self.assertRaisesRegex(OSError, 'Cannot launch'):
                apply_plan(plan, checker=Mock(), restarter=restart)
            self.assertEqual((Path(installation.root) / 'Pictide.exe').read_text(), 'previous')
            self.assertEqual(restart.call_count, 2)

    def test_unsafe_archives_and_overlapping_data_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, installation, service = fixture(Path(directory))
            self.assertEqual(install_reason(installation, Path(installation.root) / '_internal/user-data'), 'data_inside_program')
            archive = paths.cache / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('Pictide/../../outside.txt', 'escape')
            release = replace(service.release, asset={'unpacked_bytes': 1000})
            with self.assertRaisesRegex(ValueError, 'Unexpected path'):
                extract_package(archive, paths.cache / 'bad', release, installation)
            self.assertFalse((paths.cache / 'outside.txt').exists())

    def test_readonly_task_guard_includes_uncertain_remote_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'state.sqlite3'
            self.assertFalse(unfinished_jobs(database))
            with open_database(database) as connection:
                connection.execute('CREATE TABLE jobs(status TEXT, backend_pending INTEGER)')
                connection.execute("INSERT INTO jobs VALUES ('completed',0)")
            self.assertFalse(unfinished_jobs(database))
            with open_database(database) as connection:
                connection.execute("INSERT INTO jobs VALUES ('unknown',1)")
            self.assertTrue(unfinished_jobs(database))


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_current_or_newer_version_is_a_success_without_download(self):
        from backend.update_cli import run
        for running in (False, True):
            for latest in ('0.5.0', '0.4.9'):
                with self.subTest(running=running, latest=latest), tempfile.TemporaryDirectory() as directory:
                    paths, installation, prepared = fixture(Path(directory))
                    release = replace(prepared.release, version=latest, compatible=False, reason='already_current')
                    service = UpdateService(paths, installation=installation, discover=Mock(return_value=release))
                    result = dict(phase='current', current_version='0.5.0', latest_version=latest, error=None)
                    args = SimpleNamespace(data_dir=str(paths.root), check_updates=False, update=True)
                    with patch('backend.update_cli.UpdateService', return_value=service), \
                         patch('backend.update_cli.running_instance', return_value={'url': 'http://127.0.0.1:1'} if running else None), \
                         patch('backend.update_cli.local_json', return_value=result) as request, \
                         patch.object(service, 'start_download') as download, \
                         patch('backend.update_cli.launch_helper') as launch, redirect_stdout(io.StringIO()):
                        self.assertEqual(await run(args), 0)
                    download.assert_not_called()
                    launch.assert_not_called()
                    if running:
                        request.assert_called_once_with('http://127.0.0.1:1/api/updates/check', method='POST')

    async def test_cli_update_uses_the_shared_verified_download_and_install_plan(self):
        from backend.update_cli import run
        with tempfile.TemporaryDirectory() as directory:
            paths, installation, prepared = fixture(Path(directory))
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as bundle:
                for path in prepared.package.rglob('*'):
                    if path.is_file():
                        bundle.write(path, 'Pictide/' + path.relative_to(prepared.package).as_posix())
            content = buffer.getvalue()
            asset = dict(name='pictide-0.5.1-win32-amd64.zip', bytes=len(content), unpacked_bytes=10000,
                         sha256=hashlib.sha256(content).hexdigest(), url=PAGE + '/download/v0.5.1/fixture.zip')
            service = UpdateService(paths, installation=installation, discover=Mock(return_value=replace(prepared.release, asset=asset)),
                                    opener=Mock(return_value=io.BytesIO(content)))
            args = SimpleNamespace(data_dir=str(paths.root), check_updates=False, update=True, port=8189,
                                   host='127.0.0.1', lan=False, cli=True, no_browser=True, desktop=False)
            with patch('backend.update_cli.UpdateService', return_value=service), patch('backend.update_cli.launch_helper') as launch, redirect_stdout(io.StringIO()):
                self.assertEqual(await run(args), 0)
            launch.assert_called_once()
            plan = json.loads(launch.call_args.args[0].read_text(encoding='utf8'))
            self.assertEqual(plan['version'], '0.5.1')
            self.assertIn('--cli', plan['restart_args'])
            self.assertEqual(plan['data'], str(paths.root))
            self.assertEqual(list(paths.models.iterdir()), [])

    async def test_download_is_explicit_and_corrupt_download_never_becomes_installable(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, installation, source = fixture(Path(directory))
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w') as bundle:
                for path in source.package.rglob('*'):
                    if path.is_file():
                        bundle.write(path, 'Pictide/' + path.relative_to(source.package).as_posix())
            data = archive.getvalue()
            asset = dict(name='pictide-0.5.1-win32-amd64.zip', bytes=len(data), unpacked_bytes=10000,
                         sha256=hashlib.sha256(data).hexdigest(), url=PAGE + '/download/v0.5.1/fixture.zip')
            opener = Mock(return_value=io.BytesIO(data))
            service = UpdateService(paths, installation=installation, discover=Mock(return_value=replace(source.release, asset=asset)), opener=opener)
            self.assertEqual(service.status()['phase'], 'idle')
            opener.assert_not_called()
            await service.check()
            opener.assert_not_called()
            service.start_download()
            await service.task
            self.assertTrue(service.status()['can_install'])
            self.assertEqual(service.status()['phase'], 'ready')
            opener.assert_called_once()
            # A fresh launch with an existing archive still does nothing until the user acts.
            fresh = UpdateService(paths, installation=installation, opener=Mock(side_effect=AssertionError('automatic download')))
            self.assertEqual(fresh.status()['phase'], 'idle')
            self.assertFalse(fresh.status()['can_install'])
            cached = paths.cache / 'updates/0.5.1' / asset['name']
            cached.unlink()
            bad = UpdateService(paths, installation=installation, discover=Mock(return_value=replace(source.release, asset=asset)), opener=Mock(return_value=io.BytesIO(b'x' * len(data))))
            await bad.check()
            bad.start_download()
            await bad.task
            self.assertEqual(bad.status()['phase'], 'error')
            self.assertFalse(bad.status()['can_install'])
            self.assertFalse(cached.exists())


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_and_state_reads_never_check_releases_and_task_guard_blocks_install(self):
        with tempfile.TemporaryDirectory() as directory:
            paths, installation, prepared = fixture(Path(directory))
            with patch.object(host, "STATIC", paths.tmp):
                app = host.create_app(paths.root)
            application = app[host.APPLICATION]
            service = application.updates
            service.installation = installation
            service.discover = Mock(return_value=prepared.release)
            app[host.UPDATE_START] = dict(arguments=['--cli'], pids=[])
            async with TestClient(TestServer(app)) as client:
                for endpoint in ('/api/bootstrap', '/api/updates', '/api/settings/general', '/api/updates'):
                    response = await client.get(endpoint)
                    self.assertEqual(response.status, 200)
                service.discover.assert_not_called()
                response = await client.post('/api/updates/check', json={})
                self.assertEqual(response.status, 200)
                service.discover.assert_called_once()
                response = await client.post('/api/updates/download', json={'url': 'https://example.invalid/'})
                self.assertEqual(response.status, 400)
                service.package = prepared.package
                service.state['phase'] = 'ready'
                with patch('backend.store.update_state.unfinished_jobs', return_value=True), patch('backend.updates.apply.launch_helper') as launch:
                    response = await client.post('/api/updates/install', json={})
                    self.assertEqual(response.status, 409)
                    self.assertFalse(application.update_installing)
                    launch.assert_not_called()
                with patch('backend.updates.apply.launch_helper') as launch, patch('backend.host.stop_for_update'):
                    response = await client.post('/api/updates/install', json={})
                    self.assertEqual(response.status, 200)
                    self.assertEqual((await response.json())['phase'], 'installing')
                    response = await client.post('/api/settings/general', json={})
                    self.assertEqual(response.status, 503)
                    launch.assert_called_once()


class CliTests(unittest.TestCase):
    def test_help_checks_the_runtime_without_preparing_data_or_starting_services(self):
        with patch.object(host.PictideApplication, 'prepare_startup', side_effect=AssertionError('prepared data')):
            with patch.object(host, 'create_app', side_effect=AssertionError('started service')):
                with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit:
                    host._main(['--help'])
        self.assertEqual(exit.exception.code, 0)

    def test_check_flag_skips_startup_setup_and_downloads(self):
        result = dict(current_version='0.5.0', latest_version='0.5.1', error=None)
        service = SimpleNamespace(check=AsyncMock(return_value=result), close=AsyncMock())
        with patch('backend.update_cli.UpdateService', return_value=service), patch.object(host.PictideApplication, 'prepare_startup', side_effect=AssertionError('prepared model')):
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit:
                host._main(['--check-updates'])
            self.assertEqual(exit.exception.code, 0)
        service.check.assert_awaited_once()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit:
            host._main(['--check-updates', '--update'])
        self.assertEqual(exit.exception.code, 2)
