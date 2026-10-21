"""Extract and start a native portable ZIP with isolated, disposable user data."""
import argparse
from contextlib import closing, contextmanager
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.updates.files import filesystem_path


@contextmanager
def temporary_workspace():
    parent = Path(tempfile.gettempdir()).resolve()
    directory = Path(tempfile.mkdtemp(prefix='pictide-smoke-', dir=parent)).resolve()
    assert directory.parent == parent
    try:
        yield directory
    finally:
        shutil.rmtree(filesystem_path(directory))


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        path = attributes.get('src') if tag == 'script' else attributes.get('href') if tag == 'link' else None
        if path and path.startswith('/static/ui/'):
            self.paths.add(path)


def unpack(archive, directory):
    directory = Path(directory)
    if sys.platform == 'darwin':
        directory.mkdir(parents=True, exist_ok=True)
        subprocess.run(['/usr/bin/ditto', '-x', '-k', str(archive), str(directory)], check=True)
        package = directory / 'Pictide.app'
        for path in package.rglob('*'):
            if path.is_symlink() and (not path.exists() or not path.resolve().is_relative_to(package.resolve())):
                raise RuntimeError('App bundle contains a broken or external symlink: ' + str(path))
        executable = package / 'Contents/MacOS/PictideService'
        launcher = package / 'Contents/MacOS/Pictide'
        framework = package / 'Contents/Frameworks/Python.framework'
        if not framework.is_dir() or not (package / 'Contents/Frameworks/Python').is_file():
            raise RuntimeError('App bundle is missing its Python framework or library link')
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(package)], check=True)
        subprocess.run(['/usr/bin/codesign', '--verify', str(framework)], check=True)
        licenses = package / 'Contents/Resources/licenses'
        if json.loads((licenses / 'versions.json').read_text())['truststore'] != '0.10.5':
            raise RuntimeError('Missing or unexpected macOS truststore dependency')
        if not (licenses / 'truststore/LICENSE').is_file():
            raise RuntimeError('Missing truststore license')
        for entry in (executable, launcher):
            if not entry.is_file() or not os.access(entry, os.X_OK):
                raise RuntimeError('Missing executable app entry: ' + str(entry))
            result = subprocess.run([str(entry), '--help'], capture_output=True, text=True, timeout=30, check=True)
            if '--data-dir' not in result.stdout:
                raise RuntimeError('App entry did not delegate command-line help: ' + str(entry))
        subprocess.run([str(launcher), '--launcher-self-test'], capture_output=True, text=True, timeout=30, check=True)
        return executable
    links = []
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            path = directory / item.filename
            if not path.resolve().is_relative_to(directory.resolve()):
                raise RuntimeError('Archive contains a path outside the package')
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                if os.name == 'nt':
                    raise RuntimeError('Windows portable ZIP must contain regular files')
                target = os.fsdecode(bundle.read(item))
                if os.path.isabs(target) or not (path.parent / target).resolve().is_relative_to(directory.resolve()):
                    raise RuntimeError('Archive symlink points outside the package')
                links.append((path, target))
                continue
            bundle.extract(item, directory)
            if os.name != 'nt' and not item.is_dir():
                path.chmod(stat.S_IMODE(mode))
    for path, target in links:
        if not path.resolve().is_relative_to(directory.resolve()):
            raise RuntimeError('Archive symlink path points outside the package')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
    for path, _ in links:
        if not path.resolve().is_relative_to(directory.resolve()) or not path.exists():
            raise RuntimeError('Archive contains a broken or external symlink')
    root = directory / 'Pictide'
    executable = root / 'Pictide.exe' if sys.platform == 'win32' else root / 'data/runtime/pictide/Pictide'
    entries = (executable,) if sys.platform == 'win32' else (executable, root / 'start.sh')
    for path in entries:
        if not path.is_file():
            raise RuntimeError('Missing portable entry: ' + str(path))
        if os.name != 'nt' and not os.access(path, os.X_OK):
            raise RuntimeError('Archive lost executable permissions: ' + str(path))
    return executable


def stop(process):
    if os.name == 'nt':
        # A frozen Windows executable may create a child process.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=10)


def smoke(archive, report_path, timeout=900, model_dir=None):
    archive = Path(archive).resolve()
    report_path = Path(report_path).resolve()
    report = dict(passed=False, archive=archive.name, platform=sys.platform, checks=[])
    started = time.monotonic()
    failure = None
    with temporary_workspace() as temporary:
        directory = Path(temporary)
        process = None
        log_path = directory / 'startup.log'
        try:
            executable = unpack(archive, directory / 'unpacked')
            report['checks'].append('archive entries and native executable permissions')
            if sys.platform == 'darwin':
                report['checks'].append('macOS ditto roundtrip, framework links, signatures, both entry help commands and native launcher self-test')
            internal = executable.parent.parent / 'Frameworks' if sys.platform == 'darwin' else executable.parent / '_internal'
            manifest = json.loads((internal / 'resources/manifest.json').read_text(encoding='utf-8'))
            catalog = json.loads((internal / 'backend/recommendation/model.json').read_text(encoding='utf-8'))
            if manifest['model'] != catalog or any(not item['path'].startswith('libraries/') for item in manifest['files']):
                raise RuntimeError('Portable resources must contain only vocabulary files and the locked model catalog')
            if any(path.name == 'model.onnx' or path.suffix == '.safetensors' for path in internal.rglob('*')):
                raise RuntimeError('Portable archive must not bundle model weights')
            report['checks'].append('vocabulary-only seed, locked model catalog and no bundled model weights')
            data = directory / 'fresh-data'
            if model_dir is not None:
                target = data / 'models/minilm'
                target.mkdir(parents=True)
                for item in catalog['files']:
                    source = Path(model_dir) / item['path']
                    with source.open('rb') as handle:
                        actual = hashlib.file_digest(handle, 'sha256').hexdigest()
                    if source.stat().st_size != item['bytes'] or actual != item['sha256']:
                        raise RuntimeError('Warm-start model failed verification: ' + str(source))
                    shutil.copyfile(source, target / item['path'])
                report['model_source'] = 'verified local model (warm startup)'
            else:
                report['model_source'] = 'first-start download'
            with closing(socket.socket()) as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            base = f'http://127.0.0.1:{port}'
            opener = build_opener(ProxyHandler({}))

            def get(path, *, document=True):
                if urlsplit(path).netloc:
                    raise RuntimeError('Smoke requests must remain local')
                with opener.open(base + path, timeout=5) as response:
                    payload = response.read()
                    if response.status != 200:
                        raise RuntimeError('Unexpected HTTP status for ' + path)
                    return json.loads(payload) if document else payload

            environment = os.environ.copy()
            # The explicit data directory wins over inherited development settings.
            environment['PICTIDE_DATA_DIR'] = environment['PICTIDE_WEB_DATA_DIR'] = str(data)
            environment.pop('HF_HUB_OFFLINE', None)
            command = [str(executable), '--cli', '--data-dir', str(data), '--host', '127.0.0.1',
                       '--port', str(port), '--no-browser']
            if sys.platform == 'darwin':
                command.append('--desktop-worker')
                environment['PICTIDE_DESKTOP_PARENT_PIPE'] = '1'
                environment['PICTIDE_DESKTOP_STATUS'] = str(directory / 'worker.status')
            with log_path.open('wb') as log:
                process = subprocess.Popen(command, cwd=executable.parent,
                                           stdin=subprocess.PIPE if sys.platform == 'darwin' else None,
                                           stdout=log, stderr=subprocess.STDOUT, env=environment,
                                           start_new_session=os.name != 'nt',
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                deadline = time.monotonic() + timeout
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Portable process exited before becoming ready')
                    try:
                        if sys.platform == 'darwin' and (not (directory / 'worker.status').exists()
                                or (directory / 'worker.status').read_text() != 'ready'):
                            raise ConnectionError('Desktop worker is still preparing')
                        bootstrap = get('/api/bootstrap')
                        break
                    except (URLError, TimeoutError, ConnectionError):
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Portable startup timed out') from None
                        time.sleep(0.3)
                if bootstrap['name'] != 'Pictide' or Path(bootstrap['data_directory']).resolve() != data.resolve():
                    raise RuntimeError('Unexpected bootstrap or data directory')
                if sys.platform == 'darwin':
                    if (directory / 'worker.status').read_text() != 'ready':
                        raise RuntimeError('Desktop worker did not report startup readiness')
                    report['checks'].append('macOS desktop worker reserved-port startup and readiness notification')
                if bootstrap['jobs'] or bootstrap['artifacts'] or bootstrap['backends']:
                    raise RuntimeError('Fresh portable data must not contain personal records or backend credentials')
                report['version'] = bootstrap['version']
                report['checks'].append('HTTP bootstrap with fresh isolated data and no generation jobs')
                recommendation = bootstrap['recommendation']
                if not recommendation['available'] or recommendation.get('error'):
                    raise RuntimeError('Downloaded recommendation dependency is unavailable: ' + str(recommendation))
                for item in catalog['files']:
                    model_file = data / 'models/minilm' / item['path']
                    with model_file.open('rb') as handle:
                        actual = hashlib.file_digest(handle, 'sha256').hexdigest()
                    if model_file.stat().st_size != item['bytes'] or actual != item['sha256']:
                        raise RuntimeError('Startup model failed verification: ' + item['path'])
                report['checks'].append('verified downloaded model before HTTP readiness and recommendation availability')
                html = get('/', document=False).decode('utf-8')
                assets = Assets()
                assets.feed(html)
                if not assets.paths:
                    raise RuntimeError('Frontend index does not reference built static assets')
                for path in sorted(assets.paths):
                    if not get(path, document=False):
                        raise RuntimeError('Empty frontend asset: ' + path)
                report['checks'].append('frontend index and referenced script/style assets')
                dataset = get('/api/candidate/dataset')
                libraries = get('/api/candidate/library')
                if dataset['status'] != 'ready' or dataset['tag_count'] <= 0 or not libraries['selected']:
                    raise RuntimeError('Bundled vocabulary was not initialized and selected')
                with closing(sqlite3.connect((data / 'libraries' / libraries['selected']).as_uri() + '?mode=ro', uri=True)) as db:
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Initialized vocabulary failed integrity check')
                report['vocabulary'] = dataset
                report['checks'].append('initialized vocabulary selection and SQLite integrity')
                if sys.platform == 'darwin':
                    process.stdin.close()
                    if process.wait(timeout=15) != 0:
                        raise RuntimeError('Desktop worker did not stop cleanly after its owner pipe closed')
                    report['checks'].append('macOS owner-pipe closure stops the desktop worker cleanly')
                if process.poll() is None:
                    stop(process)
                process = None
                from scripts.smoke_updates import smoke as update_smoke
                update_smoke(executable, data, base, archive)
                report['updates_verified'] = True
                report['checks'].append('native updater helper: replacement, readiness, restart, failed-start rollback and personal-data/model preservation')
                report['passed'] = True
        except Exception as error:
            failure = error
            report['error'] = str(error)
        finally:
            if process is not None:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                stop(process)
            if not report['passed'] and log_path.exists():
                report['startup_log_tail'] = log_path.read_text(encoding='utf-8', errors='replace')[-16000:]
            report['seconds'] = round(time.monotonic() - started, 2)
            with archive.open('rb') as source:
                report['archive_sha256'] = hashlib.file_digest(source, 'sha256').hexdigest()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if failure is not None:
        raise RuntimeError(f'Smoke failed; see {report_path}: {failure}') from failure
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=900)
    parser.add_argument('--model-dir', type=Path,
                        help='Optional verified MiniLM snapshot to seed a warm-start smoke; omitted for a real first-start download')
    arguments = parser.parse_args()
    smoke(arguments.archive, arguments.report, arguments.timeout, arguments.model_dir)
