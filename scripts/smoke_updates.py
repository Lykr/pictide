"""Exercise the native updater with disposable data and an optional previous release."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.paths import DataPaths
from backend.network import open_url
from backend.updates.apply import create_plan, launch_helper, local_json, child_environment
from backend.updates.contracts import Installation, Release
from backend.updates.service import UpdateService
from backend.updates.installation import executable as package_executable, extract_package, package_metadata
from backend.updates.processes import running_pids
from backend.updates.releases import API, PAGE, read_json, version


def download_previous(archive, destination):
    """CI-only: fetch the latest stable native archive if it precedes this build."""
    from backend import __version__
    document = read_json(API)
    previous = document['tag_name'].removeprefix('v')
    if version(previous) >= version(__version__.split('-')[0]):
        return None
    allowed = json.loads((ROOT / 'scripts/update-policy.json').read_text())['direct_upgrade_from']
    if not version(allowed['minimum']) <= version(previous) < version(allowed['maximum_exclusive']):
        return None
    suffix = Path(archive).name.removeprefix('pictide-' + __version__ + '-')
    name = 'pictide-' + previous + '-' + suffix
    asset = next(item for item in document['assets'] if item['name'] == name)
    if asset['browser_download_url'] != PAGE + '/download/v' + previous + '/' + name:
        raise RuntimeError('Unexpected previous-release asset location')
    destination.mkdir(parents=True)
    target = destination / name
    with open_url(asset['browser_download_url'], timeout=60) as source, target.open('wb') as output:
        shutil.copyfileobj(source, output)
    if target.stat().st_size != asset['size']:
        raise RuntimeError('Previous-release download size mismatch')
    with target.open('rb') as stream:
        digest = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
    if asset.get('digest') and asset['digest'] != digest:
        raise RuntimeError('Previous-release download checksum mismatch')
    return target


def smoke(executable, data, base, archive, previous_archive=None):
    from scripts.smoke_portable import unpack, stop
    target_package = executable.parents[2] if sys.platform == 'darwin' else (
        executable.parents[3] if sys.platform == 'linux' else executable.parent)
    info = package_metadata(target_package, sys.platform)
    if previous_archive:
        executable = unpack(previous_archive, data.parent / 'previous-release')
        previous_data = DataPaths(data.parent / 'previous-data').ensure()
        shutil.copytree(data / 'models/minilm', previous_data.models / 'minilm')
        data = previous_data.root
    paths = DataPaths(data)
    root = executable.parents[2].parent if sys.platform == 'darwin' else (
        executable.parents[3] if sys.platform == 'linux' else executable.parent)
    arguments = ['--cli', '--no-browser', '--data-dir', str(data), '--host', '127.0.0.1',
                 '--port', str(urlsplit(base).port)]

    def ready(expected=None, process=None):
        deadline = time.monotonic() + 120
        while True:
            if process is not None and process.poll() is not None:
                raise RuntimeError('Previous application exited; see previous-startup.log')
            try:
                result = local_json(base + '/api/bootstrap')
                if result['data_directory'] != str(data) or expected and result['version'] != expected:
                    raise RuntimeError('Unexpected restarted version or data directory')
                return result
            except (OSError, ValueError):
                if time.monotonic() > deadline:
                    raise RuntimeError('Native application did not become ready')
                time.sleep(.2)

    with (data.parent / 'previous-startup.log').open('wb') as log:
        previous = subprocess.Popen([str(executable), *arguments], stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, env=child_environment(), start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            old_version = ready(process=previous)['version']
            if previous_archive and version(old_version) >= version(info['version'].split('-')[0]):
                raise RuntimeError('Cross-version smoke requires an older application')
            local_json(base + '/api/settings/general', method='PUT', payload={'theme': 'dark'})
        finally:
            stop(previous)
    installation = Installation(str(root), sys.platform, info['arch'], old_version)
    with zipfile.ZipFile(archive) as bundle:
        size = sum(item.file_size for item in bundle.infolist()) + 1024 * 1024
    release = Release(info['version'], '', True, '', {'unpacked_bytes': size})
    service = UpdateService(paths, installation=installation)
    service.release = release
    marker = paths.images / 'updater-preservation-smoke.txt'
    marker.write_text('Keep user data', encoding='utf8')
    weights = paths.models / 'minilm/model.onnx'
    with weights.open('rb') as stream:
        previous_model = hashlib.file_digest(stream, 'sha256').hexdigest()
    with closing(sqlite3.connect(paths.database)) as db, db:
        db.execute('CREATE TABLE updater_smoke_evidence(value TEXT)')
        db.execute("INSERT INTO updater_smoke_evidence VALUES ('previous version data')")

    for expected in ('rolled_back', 'installed'):
        service.package = extract_package(archive, paths.cache / 'updates' / info['version'] / 'unpacked', release, installation)
        service.state.update(phase='ready', compatible=True)
        plan, helper = create_plan(service, arguments, [])
        if (plan.parent / 'helper').exists():
            raise RuntimeError('Updater copied an unnecessary helper runtime')
        if expected == 'rolled_back':
            # Leave the staged service runnable; fail copying a program file or launching the macOS UI.
            damaged = package_executable(service.package, sys.platform) if sys.platform == 'darwin' else service.package / 'README.txt'
            damaged.unlink()
        child = launch_helper(plan, helper)
        try:
            try:
                code = child.wait(timeout=240)
            except subprocess.TimeoutExpired:
                raise RuntimeError('Native update helper timed out') from None
            if (code == 0) != (expected == 'installed'):
                raise RuntimeError('Native update helper failed: ' + (plan.parent / 'apply.log').read_text(encoding='utf8', errors='replace')[-12000:])
            result = json.loads((paths.tmp / 'updates/result.json').read_text(encoding='utf8'))
            ready(info['version'] if expected == 'installed' else old_version)
            if result['phase'] != expected or local_json(base + '/api/settings/general')['theme'] != 'dark':
                raise RuntimeError('Update result or existing settings were not preserved')
            with closing(sqlite3.connect(paths.database)) as db:
                if db.execute('SELECT value FROM updater_smoke_evidence').fetchone()[0] != 'previous version data':
                    raise RuntimeError('Update changed existing database records')
            snapshots = list((Path(result['backup']) / 'db').glob('*.sqlite3'))
            if not snapshots:
                raise RuntimeError('Update did not retain database backups')
            for snapshot in snapshots:
                with closing(sqlite3.connect(snapshot.as_uri() + '?mode=ro', uri=True)) as db:
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Database backup failed integrity check')
            with weights.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != previous_model or marker.read_text() != 'Keep user data':
                    raise RuntimeError('Update changed personal files or model weights')
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
            for pid in running_pids(installation):
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, check=False)
                else:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            deadline = time.monotonic() + 15
            while running_pids(installation):
                if time.monotonic() > deadline:
                    raise RuntimeError('Native update smoke worker did not stop')
                time.sleep(.1)
    return dict(from_version=old_version, to_version=info['version'], cross_version=old_version != info['version'])
