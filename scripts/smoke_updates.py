"""Native updater smoke invoked after the portable service/model smoke, with disposable data."""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import zipfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.paths import DataPaths
from backend.updates.apply import create_plan, launch_helper, local_json
from backend.updates.contracts import Installation, Release
from backend.updates.service import UpdateService
from backend.updates.installation import executable as package_executable, extract_package
from backend.updates.processes import running_pids


def smoke(executable, data, base, archive):
    paths = DataPaths(data)
    if sys.platform == 'darwin':
        original = executable.parents[2]
        root = original.parent
        metadata = original / 'Contents/Frameworks/resources/installation.json'
    else:
        root = executable.parents[3] if sys.platform == 'linux' else executable.parent
        original = root
        metadata = executable.parent / '_internal/resources/installation.json'
    info = json.loads(metadata.read_text(encoding='utf8'))
    installation = Installation(str(root), sys.platform, info['arch'], info['version'])
    stage = paths.cache / 'updates' / info['version'] / 'unpacked' / original.name
    with zipfile.ZipFile(archive) as bundle:
        size = sum(item.file_size for item in bundle.infolist()) + 1024 * 1024
    release = Release(info['version'], '', True, '', {'unpacked_bytes': size})
    stage = extract_package(archive, stage.parent, release, installation)
    service = UpdateService(paths, installation=installation)
    service.package = stage
    service.release = release
    service.state.update(phase='ready', compatible=True)
    marker = paths.images / 'updater-preservation-smoke.txt'
    marker.write_text('Keep user data', encoding='utf8')
    weights = paths.models / 'minilm/model.onnx'
    with weights.open('rb') as stream:
        previous_model = hashlib.file_digest(stream, 'sha256').hexdigest()
    port = str(urlsplit(base).port)
    arguments = ['--cli', '--no-browser', '--data-dir', str(data), '--host', '127.0.0.1', '--port', port]
    for expected in ('installed', 'rolled_back'):
        plan, helper = create_plan(service, arguments, [])
        if expected == 'rolled_back':
            package_executable(stage, sys.platform, service=True).write_bytes(b'Invalid executable for rollback verification')
        worker = None
        child = launch_helper(plan, helper)
        try:
            try:
                code = child.wait(timeout=240)
            except subprocess.TimeoutExpired:
                raise RuntimeError('Native update helper timed out') from None
            if (code == 0) != (expected == 'installed'):
                raise RuntimeError('Native update helper failed: ' + (plan.parent / 'apply.log').read_text(encoding='utf8', errors='replace')[-12000:])
            result = json.loads((paths.tmp / 'updates/result.json').read_text(encoding='utf8'))
            deadline = time.monotonic() + 60
            while True:
                try:
                    bootstrap = local_json(base + '/api/bootstrap')
                    worker = json.loads((paths.tmp / 'service-instance.json').read_text(encoding='utf8'))['pid']
                    break
                except (OSError, ValueError):
                    if time.monotonic() > deadline:
                        raise RuntimeError('Native application did not restart after updating')
                    time.sleep(.2)
            if result['phase'] != expected or bootstrap['version'] != info['version'] or bootstrap['data_directory'] != str(data):
                raise RuntimeError('Unexpected update result or restarted data directory')
            snapshots = list((Path(result['backup']) / 'db').glob('*.sqlite3'))
            if not snapshots:
                raise RuntimeError('Update did not retain database backups')
            for snapshot in snapshots:
                with closing(sqlite3.connect(snapshot.as_uri() + '?mode=ro', uri=True)) as database:
                    if database.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Database backup failed integrity check')
            if marker.read_text(encoding='utf8') != 'Keep user data':
                raise RuntimeError('Update modified personal files')
            with weights.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != previous_model:
                    raise RuntimeError('Update changed existing recommendation weights')
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
            if worker is None:
                record_path = paths.tmp / 'service-instance.json'
                if record_path.exists():
                    record = json.loads(record_path.read_text(encoding='utf8'))
                    if record.get('data_directory') == str(data) and record.get('installation') == str(root):
                        worker = record['pid']
            if worker:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(worker), '/T', '/F'], capture_output=True, check=False)
                else:
                    try:
                        os.killpg(worker, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            deadline = time.monotonic() + 15
            while worker in running_pids(installation):
                if time.monotonic() > deadline:
                    raise RuntimeError('Native update smoke worker did not stop')
                time.sleep(.1)
