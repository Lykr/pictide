"""Extract and start a native portable ZIP with isolated, disposable user data."""
import argparse
from contextlib import closing
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
    executable = root / 'data/runtime/pictide' / ('Pictide.exe' if os.name == 'nt' else 'Pictide')
    launcher = root / ('start.cmd' if os.name == 'nt' else 'start.command' if sys.platform == 'darwin' else 'start.sh')
    for path in (executable, launcher):
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
    with tempfile.TemporaryDirectory(prefix='pictide-smoke-') as temporary:
        directory = Path(temporary)
        process = None
        log_path = directory / 'startup.log'
        try:
            executable = unpack(archive, directory / 'unpacked')
            report['checks'].append('archive entries and native executable permissions')
            internal = executable.parent / '_internal'
            manifest = json.loads((internal / 'resources/manifest.json').read_text(encoding='utf-8'))
            catalog = json.loads((internal / 'backend/recommand/model.json').read_text(encoding='utf-8'))
            if manifest['model'] != catalog or any(not item['path'].startswith('libraries/') for item in manifest['files']):
                raise RuntimeError('Portable resources must contain only vocabulary files and the locked model catalog')
            if any(path.name == 'model.onnx' or path.suffix == '.safetensors' for path in executable.parent.rglob('*')):
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
            with log_path.open('wb') as log:
                process = subprocess.Popen([str(executable), '--data-dir', str(data), '--host', '127.0.0.1',
                                            '--port', str(port), '--no-browser'], cwd=executable.parent,
                                           stdout=log, stderr=subprocess.STDOUT, env=environment,
                                           start_new_session=os.name != 'nt',
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                deadline = time.monotonic() + timeout
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Portable process exited before becoming ready')
                    try:
                        bootstrap = get('/api/bootstrap')
                        break
                    except (URLError, TimeoutError, ConnectionError):
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Portable startup timed out') from None
                        time.sleep(0.3)
                if bootstrap['name'] != 'Pictide' or Path(bootstrap['data_directory']).resolve() != data.resolve():
                    raise RuntimeError('Unexpected bootstrap or data directory')
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
                report['passed'] = True
        except Exception as error:
            failure = error
            report['error'] = str(error)
        finally:
            if process is not None:
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
