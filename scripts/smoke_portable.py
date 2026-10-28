"""Extract and start a native portable ZIP with isolated, disposable user data."""
import argparse
from contextlib import closing, contextmanager
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import signal
import shutil
import socket
import sqlite3
import stat
import struct
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


def smoke_inference(data, get):
    """Exercise frozen CPU inference using an inert, completed history fixture."""
    from backend.paths import DataPaths
    from backend.store.sqlite import Repository
    data = Path(data)
    fixture = data.parent / 'inference-fixture.sqlite3'
    storage = Repository(fixture)
    storage.save_backend({'id': 'cpu-smoke', 'name': 'CPU smoke fixture', 'kind': 'comfyui',
                          'base_url': 'http://127.0.0.1:1', 'api_key': ''})
    texts = ('garden', 'blue sky')
    positive = ', '.join(texts)
    state = storage.ensure_roam('cpu-smoke', None, 1,
        {'backend_id': 'cpu-smoke', 'request_id': 'cpu-smoke', 'positive': positive, 'negative': '', 'seed': 42},
        {'candidate_id': 'cpu-smoke', 'positive': positive, 'negative': '',
         'terms': [{'text': text, 'channel': 'positive'} for text in texts]})
    storage.complete(state['job']['id'], [{'node_id': '9', 'index': 0, 'filename': 'cpu-smoke.png'}])
    artifact = storage.artifacts(source='roam')[0]['id']
    database = DataPaths(data).database
    # Publish completed history atomically: the running worker never sees queued
    # work, and no active backend or image/LLM request is created.
    with closing(sqlite3.connect(database)) as db:
        db.execute('ATTACH DATABASE ? AS fixture', (str(fixture),))
        with db:
            db.execute('BEGIN IMMEDIATE')
            for table in ('backend_revisions', 'jobs', 'artifacts', 'roam_jobs'):
                db.execute(f'INSERT INTO main.{table} SELECT * FROM fixture.{table}')
        if db.execute('SELECT count(*) FROM recommendation_vectors').fetchone()[0]:
            raise RuntimeError('CPU inference smoke requires an empty embedding cache')
    score = get(f'/api/artifacts/{artifact}/preference-score', timeout=60)
    if score.get('status') != 'scored' or not isinstance(score.get('score'), (int, float)) or not math.isfinite(score['score']):
        raise RuntimeError('Native CPU MiniLM scoring failed: ' + str(score))
    with closing(sqlite3.connect(database)) as db:
        vectors = dict(db.execute('SELECT text,vector FROM recommendation_vectors'))
    if set(vectors) != set(texts):
        raise RuntimeError('Native CPU MiniLM did not persist the expected embeddings')
    for vector_data in vectors.values():
        if len(vector_data) != 384 * 4:
            raise RuntimeError('Native MiniLM embedding has the wrong dimension')
        vector = struct.unpack('<384f', vector_data)
        if not all(math.isfinite(value) for value in vector) or not 0.99 < sum(value * value for value in vector) < 1.01:
            raise RuntimeError('Native MiniLM embedding is not finite and normalized')
    return {'texts': list(texts), 'dimension': 384, 'status': score['status']}


def smoke(archive, report_path, timeout=900, model_dir=None, previous_archive=None, previous_release=False):
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
            vocabulary_catalog = json.loads((internal / 'backend/setup/vocabularies.json').read_text(encoding='utf-8'))
            if manifest['model'] != catalog or manifest['vocabularies'] != vocabulary_catalog or manifest['files']:
                raise RuntimeError('Portable resources must contain only locked download catalogs')
            if any(path.name == 'model.onnx' or path.suffix in {'.safetensors', '.sqlite3'} for path in internal.rglob('*')):
                raise RuntimeError('Portable archive must not bundle vocabularies or model weights')
            report['checks'].append('locked vocabulary/model download catalogs; no bundled vocabularies or model weights')
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

            def get(path, *, document=True, timeout=5):
                if urlsplit(path).netloc:
                    raise RuntimeError('Smoke requests must remain local')
                with opener.open(base + path, timeout=timeout) as response:
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
                    raise RuntimeError('Downloaded vocabulary was not initialized and selected')
                with closing(sqlite3.connect((data / 'libraries' / libraries['selected']).as_uri() + '?mode=ro', uri=True)) as db:
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Initialized vocabulary failed integrity check')
                if not libraries['selected'].startswith('pictide-vocabulary-filtered'):
                    raise RuntimeError('Unattended first startup must select filtered')
                report['vocabulary'] = dataset
                report['checks'].append('first-start downloaded vocabulary selection and SQLite integrity')
                report['inference'] = smoke_inference(data, get)
                report['checks'].append('native CPU MiniLM inference through HTTP and finite normalized 384-dimensional embeddings')
                if sys.platform == 'darwin':
                    process.stdin.close()
                    if process.wait(timeout=15) != 0:
                        raise RuntimeError('Desktop worker did not stop cleanly after its owner pipe closed')
                    report['checks'].append('macOS owner-pipe closure stops the desktop worker cleanly')
                if process.poll() is None:
                    stop(process)
                process = None
                from scripts.smoke_updates import smoke as update_smoke, download_previous
                if previous_release:
                    previous_archive = download_previous(archive, directory / 'previous-download')
                report['upgrade'] = update_smoke(executable, data, base, archive, previous_archive)
                report['updates_verified'] = report['upgrade']['cross_version']
                report['checks'].append('native updater: staged helper, replacement-failure rollback, normal restart and previous data/model preservation')
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
    previous = parser.add_mutually_exclusive_group()
    previous.add_argument('--previous-archive', type=Path, help='Older native release ZIP for a real cross-version upgrade smoke')
    previous.add_argument('--previous-release', action='store_true', help='Download the latest older stable native release for CI verification')
    arguments = parser.parse_args()
    smoke(arguments.archive, arguments.report, arguments.timeout, arguments.model_dir,
          arguments.previous_archive, arguments.previous_release)
