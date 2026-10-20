"""A few portable startup smokes; native bundling is validated separately."""
from contextlib import closing
import json
import logging
import os
from pathlib import Path
import platform
import plistlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import ANY, patch
import zipfile

from aiohttp import web
from aiohttp.test_utils import TestServer

from backend.application import PictideApplication
from backend import __version__
from backend.host import open_browser_when_ready
from backend.paths import DataPaths
from backend.recommand.resources import model_catalog
from corpus.portable import PreparedResources
from scripts.build_portable import build, export_resources, write_archive
from scripts.smoke_portable import unpack
from tests.test_candidate_libraries import vocabulary


class PortableResourcesSmoke(unittest.TestCase):
    def test_build_from_prepared_resources_without_application_data(self):
        for target in ('win32', 'darwin', 'linux'):
            with self.subTest(platform=target):
                self.check_platform_build(target)

    def check_platform_build(self, target_platform):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'clean repository'
            front = repo / 'web/dist'
            front.mkdir(parents=True)
            (front / 'index.html').write_text('frontend fixture', encoding='utf-8')
            icon = repo / 'web/public/icons/pictide-512.png'
            icon.parent.mkdir(parents=True)
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'web/public/icons/pictide-512.png', icon)
            notices = repo / 'web/src/THIRD_PARTY_NOTICES.md'
            notices.parent.mkdir(parents=True)
            notices.write_text('frontend licenses', encoding='utf-8')
            for name in ('LICENSE', 'NOTICE'):
                (repo / name).write_text('project license fixture', encoding='utf-8')
            library = vocabulary(root / 'neutral.sqlite3')
            catalog = repo / 'backend/recommand/model.json'
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps(model_catalog()), encoding='utf-8')
            workflow = repo / 'docs/assets/workflows/anima-turbo-v1.1.api.json'
            workflow.parent.mkdir(parents=True)
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'docs/assets/workflows/anima-turbo-v1.1.api.json', workflow)
            provenance = {'fixture': True, 'dataset_revision': 'pinned-v1'}
            resources = PreparedResources(library, provenance)
            dataset, cache = (root / name for name in ('datasets', 'cache'))
            profile = root / 'profile.json'
            output = root / 'release'
            output.mkdir()
            previous = output / f'pictide-{__version__}-{target_platform}-{platform.machine().lower()}.zip'
            previous.write_bytes(b'previous local build')

            commands = []

            def bundle(command, *, cwd=None, check):
                commands.append(command)
                if command[0] == '/usr/bin/xcrun':
                    Path(command[command.index('-o') + 1]).write_text('native Swift fixture', encoding='utf-8')
                    return
                if command[0] == '/usr/bin/codesign':
                    return
                self.assertEqual(cwd, repo)
                self.assertTrue(check)
                dist = Path(command[command.index('--distpath') + 1])
                if target_platform == 'darwin':
                    self.assertIn('--windowed', command)
                    bundled = dist / 'Pictide.app/Contents/MacOS'
                    internal = dist / 'Pictide.app/Contents/Frameworks'
                    (dist / 'Pictide.app/Contents/Resources').mkdir(parents=True)
                    (dist / 'Pictide.app/Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'Pictide'}))
                else:
                    bundled = dist / 'Pictide'
                    internal = bundled / '_internal'
                bundled.mkdir(parents=True)
                executable = bundled / ('Pictide.exe' if target_platform == 'win32' else 'Pictide')
                executable.write_text('native fixture', encoding='utf-8')
                for index, arg in enumerate(command[:-1]):
                    if arg == '--add-data':
                        source, destination = command[index + 1].rsplit(os.pathsep, 1)
                        target = internal / destination
                        if Path(source).is_file():
                            target.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(source, target / Path(source).name)
                        else:
                            shutil.copytree(source, target)

            def fixture_archive(package, archive):
                with zipfile.ZipFile(archive, 'w') as result:
                    for path in package.rglob('*'):
                        result.write(path, path.relative_to(package.parent).as_posix())

            logger = logging.Logger('portable-build-smoke')
            try:
                with patch('scripts.build_portable.ROOT', repo), \
                        patch('scripts.build_portable.sys.platform', target_platform), \
                        patch('scripts.build_portable.build_frontend', side_effect=lambda target: shutil.copytree(front, target)) as frontend, \
                        patch('scripts.build_portable.prepare_resources', return_value=resources) as prepare, \
                        patch('scripts.build_portable.subprocess.run', side_effect=bundle), \
                        patch('scripts.build_portable.write_archive', side_effect=fixture_archive), \
                        patch('scripts.build_portable.copy_licenses', side_effect=lambda target: (target / 'Apache-2.0.txt').write_text('license fixture')), \
                        patch('backend.paths.logging.getLogger', return_value=logger), \
                        patch.dict('os.environ'), patch('tempfile.tempdir', tempfile.tempdir), \
                        patch('sys.pycache_prefix', sys.pycache_prefix):
                    result = build(output, dataset_dir=dataset, cache_dir=cache,
                                   profile=profile)
                    prepare.assert_called_once_with(dataset, cache, profile,
                                                    prebuilt_library=None, progress=ANY)
                    frontend.assert_called_once()
            finally:
                for handler in logger.handlers:
                    handler.close()
            self.assertFalse((repo / 'data').exists())
            self.assertEqual(result['resources'], provenance)
            self.assertTrue(result['passed'])
            self.assertEqual(json.loads(Path(result['report']).read_text())['resources'], provenance)
            self.assertEqual(list(output.iterdir()), [Path(result['archive'])])
            self.assertFalse(list((repo / 'dev/build/tmp').glob('portable-build-*')))
            self.assertEqual((front / 'index.html').read_text(), 'frontend fixture')
            with zipfile.ZipFile(result['archive']) as archive:
                internal = ('Pictide.app/Contents/Frameworks/' if target_platform == 'darwin'
                            else 'Pictide/_internal/' if target_platform == 'win32'
                            else 'Pictide/data/runtime/pictide/_internal/')
                seed = internal + 'resources/'
                manifest = json.loads(archive.read(seed + 'manifest.json'))
                self.assertEqual(manifest['provenance'], provenance)
                self.assertEqual(manifest['model'], model_catalog())
                self.assertEqual([item['path'] for item in manifest['files']], ['libraries/neutral.sqlite3'])
                self.assertIn(internal + 'backend/recommand/model.json', archive.namelist())
                bundled_workflow = json.loads(archive.read(internal + 'backend/workflows/anima-turbo-v1.1.api.json'))
                self.assertEqual(bundled_workflow['28']['inputs'], dict(width=832, height=1248, batch_size=1))
                self.assertIn(seed + 'libraries/neutral.sqlite3', archive.namelist())
                names = archive.namelist()
                if target_platform == 'win32':
                    self.assertIn('Pictide/Pictide.exe', names)
                    self.assertFalse(any(name.startswith('Pictide/data/') or name.endswith('start.cmd') for name in names))
                elif target_platform == 'darwin':
                    self.assertIn('Pictide.app/Contents/MacOS/Pictide', names)
                    self.assertIn('Pictide.app/Contents/MacOS/PictideService', names)
                    self.assertIn('Pictide.app/Contents/Resources/LICENSE', names)
                    self.assertIn('Pictide.app/Contents/Resources/desktop.png', names)
                    info = plistlib.loads(archive.read('Pictide.app/Contents/Info.plist'))
                    self.assertTrue(info['LSUIElement'])
                    self.assertTrue(info['NSHighResolutionCapable'])
                    self.assertEqual(info['CFBundleShortVersionString'], __version__)
                    self.assertFalse(any(name.endswith('start.command') for name in names))
                    signing = [command for command in commands if command[0] == '/usr/bin/codesign']
                    self.assertEqual(len(signing), 4)
                    self.assertTrue(Path(signing[0][-1]).as_posix().endswith('Contents/MacOS/PictideService'))
                    self.assertTrue(Path(signing[1][-1]).as_posix().endswith('Contents/MacOS/Pictide'))
                    self.assertTrue(signing[2][-1].endswith('Pictide.app'))
                else:
                    self.assertIn('Pictide/start.sh', names)
                    self.assertIn('Pictide/data/runtime/pictide/Pictide', names)
                self.assertFalse(any(name.endswith('.onnx') or '/models/' in name for name in archive.namelist()))
                self.assertFalse(any('/db/' in name or '/images/' in name for name in archive.namelist()))
                exported = root / 'exported.sqlite3'
                exported.write_bytes(archive.read(seed + 'libraries/neutral.sqlite3'))
                with closing(sqlite3.connect(exported)) as db:
                    self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='presets'").fetchone())

    def test_macos_archive_uses_native_bundle_archiver(self):
        with patch('scripts.build_portable.sys.platform', 'darwin'), patch('scripts.build_portable.subprocess.run') as run:
            write_archive(Path('Pictide.app'), Path('native.zip'))
        run.assert_called_once_with(['/usr/bin/ditto', '-c', '-k', '--keepParent', 'Pictide.app', 'native.zip'], check=True)

    def test_macos_smoke_checks_both_native_entries_and_framework(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'unpacked'
            package = destination / 'Pictide.app'
            native = package / 'Contents/MacOS'
            native.mkdir(parents=True)
            frameworks = package / 'Contents/Frameworks'
            (frameworks / 'Python.framework').mkdir(parents=True)
            licenses = package / 'Contents/Resources/licenses'
            (licenses / 'truststore').mkdir(parents=True)
            (licenses / 'versions.json').write_text(json.dumps({'truststore': '0.10.5'}))
            (licenses / 'truststore/LICENSE').write_text('license fixture')
            for entry in (native / 'Pictide', native / 'PictideService', frameworks / 'Python'):
                entry.write_bytes(b'native fixture')
                entry.chmod(0o755)
            with patch('scripts.smoke_portable.sys.platform', 'darwin'), \
                    patch('scripts.smoke_portable.subprocess.run') as run:
                run.return_value.stdout = 'usage: Pictide --data-dir PATH'
                self.assertEqual(unpack(Path('mac.zip'), destination), native / 'PictideService')
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[0], ['/usr/bin/ditto', '-x', '-k', 'mac.zip', str(destination)])
            self.assertEqual(commands[-3:], [[str(native / 'PictideService'), '--help'], [str(native / 'Pictide'), '--help'],
                                            [str(native / 'Pictide'), '--launcher-self-test']])

    def test_failed_build_preserves_final_archives_and_writes_failure_report(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            output = repo / 'releases'
            output.mkdir()
            previous = output / f'pictide-{__version__}-{sys.platform}-{platform.machine().lower()}.zip'
            previous.write_bytes(b'previous final package')
            logger = logging.Logger('portable-failure-smoke')
            try:
                with patch('scripts.build_portable.ROOT', repo), \
                        patch('scripts.build_portable.build_frontend', side_effect=RuntimeError('frontend fixture failed')), \
                        patch('backend.paths.logging.getLogger', return_value=logger), \
                        patch.dict('os.environ'), patch('tempfile.tempdir', tempfile.tempdir), \
                        patch('sys.pycache_prefix', sys.pycache_prefix):
                    with self.assertRaisesRegex(RuntimeError, 'frontend fixture failed'):
                        build()
            finally:
                for handler in logger.handlers:
                    handler.close()
            self.assertEqual(list(output.iterdir()), [previous])
            self.assertEqual(previous.read_bytes(), b'previous final package')
            self.assertFalse(list((repo / 'dev/build/tmp').glob('portable-build-*')))
            report = next((repo / 'dev/verification/portable').rglob('build-report.json'))
            self.assertEqual(json.loads(report.read_text())['error'], 'frontend fixture failed')
            self.assertFalse(json.loads(report.read_text())['passed'])

    def test_export_initialize_and_preserve_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = vocabulary(root / 'neutral.sqlite3')
            seed = root / 'seed'
            resources = PreparedResources(library, {'fixture': True})
            manifest = export_resources(resources, seed)
            self.assertTrue(manifest['files'])
            with closing(sqlite3.connect(seed / 'libraries/neutral.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM tags').fetchone()[0], 2)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='presets'").fetchone())
            target = DataPaths(root / 'portable data')
            with patch('backend.recommand.resources.prepare_model') as prepare:
                PictideApplication.prepare_startup(target, seed)
                prepare.assert_called_once_with(target.models / 'minilm')
            target.candidate_database.write_bytes(b'personal presets')
            target.database.write_bytes(b'personal history')
            with patch('backend.recommand.resources.prepare_model'):
                PictideApplication.prepare_startup(target, seed)
            self.assertEqual(target.candidate_database.read_bytes(), b'personal presets')
            self.assertEqual(target.database.read_bytes(), b'personal history')

    def test_portable_default_uses_executable_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            cases = [('win32', root / 'Pictide/Pictide.exe', root / 'Pictide/data'),
                     ('darwin', root / 'Pictide.app/Contents/MacOS/PictideService', root / 'Library/Application Support/Pictide'),
                     ('linux', root / 'Pictide/data/runtime/pictide/Pictide', root / 'Pictide/data')]
            for target, executable, expected in cases:
                with self.subTest(platform=target), patch('backend.paths.sys.platform', target), \
                        patch('backend.paths.Path.home', return_value=root), \
                        patch('backend.paths.sys.executable', str(executable)), \
                        patch('backend.paths.sys.frozen', True, create=True), patch.dict('os.environ', {}, clear=True):
                    self.assertEqual(DataPaths().root, expected)
                    self.assertEqual(DataPaths(root / 'custom').root, root / 'custom')
                    with patch.dict('os.environ', {'PICTIDE_DATA_DIR': str(root / 'environment')}):
                        self.assertEqual(DataPaths().root, root / 'environment')


class BrowserStartupSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_opens_browser_after_bootstrap_answers(self):
        application = web.Application()
        async def bootstrap(request):
            return web.json_response({'name': 'Pictide'})
        application.router.add_get('/api/bootstrap', bootstrap)
        server = TestServer(application)
        await server.start_server()
        try:
            url = str(server.make_url('/')).rstrip('/')
            with patch('backend.host.webbrowser.open', return_value=True) as browser:
                await open_browser_when_ready(url)
                browser.assert_called_once_with(url)
        finally:
            await server.close()
