"""Independent, user-launched replacement process with a retained recovery backup."""
import ctypes
from contextlib import closing
from dataclasses import asdict
import json
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

from .contracts import Installation, PROGRAM_FILES
from .installation import executable, extract_package, install_reason, package_metadata
from .lock import UpdateLease
from .processes import running_pids
from .files import filesystem_path


def alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == 'win32':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def local_json(url, *, method='GET', token=None, payload=None):
    request = Request(url, data=json.dumps(payload or {}).encode() if method == 'POST' else None, method=method,
                      headers={'Content-Type': 'application/json', **({'X-Pictide-Update': token} if token else {})})
    with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
        return json.load(response)


def active_install(data):
    marker = Path(data) / 'tmp/updates/installing.json'
    if not marker.exists():
        return False
    return alive(json.loads(marker.read_text(encoding='utf8')).get('pid'))


def create_plan(service, restart_args, url, pids):
    with UpdateLease(service.paths.root):
        if active_install(service.paths.root):
            raise ValueError('An update installation is already running')
        path, program = _create_plan(service, restart_args, url, pids)
        (service.paths.tmp / 'updates/installing.json').write_text(json.dumps(dict(pid=os.getpid(), plan=str(path))), encoding='utf8')
        return path, program


def _create_plan(service, restart_args, url, pids):
    installation = service.installation
    reason = install_reason(installation, service.paths.root)
    if reason or not service.package or not service.release or not service.release.compatible or service.state['phase'] not in ('ready', 'preparing'):
        raise ValueError('The verified update is not ready to install: ' + reason)
    if running_pids(installation) - set(pids) - {os.getpid()}:
        raise ValueError('Close other instances using this application installation before updating.')
    if service.release.asset.get('sha256'):
        archive = service.paths.cache / 'updates' / service.release.version / service.release.asset['name']
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != service.release.asset['sha256']:
                raise ValueError('The downloaded update changed; download it again before installing.')
        service.package = extract_package(archive, archive.parent / 'unpacked', service.release, installation)
    directory = service.paths.tmp / 'updates' / secrets.token_hex(16)
    directory.mkdir(parents=True)
    helper = directory / 'helper' / service.package.name
    helper.parent.mkdir()
    shutil.copytree(filesystem_path(service.package), filesystem_path(helper), symlinks=True)
    plan = dict(schema=1, installation=asdict(installation), version=service.release.version,
                data=str(service.paths.root), package=str(service.package), url=url,
                restart_args=restart_args, pids=pids, token=secrets.token_hex(32))
    path = directory / 'plan.json'
    path.write_text(json.dumps(plan, indent=2), encoding='utf8')
    return path, executable(helper, installation.platform, service=True)


def launch_helper(path, program):
    environment = dict(os.environ)
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    for name in ('PICTIDE_DESKTOP_PARENT_PIPE', 'PICTIDE_DESKTOP_STATUS', 'PICTIDE_DESKTOP_PARENT_PID', 'PICTIDE_DESKTOP_ARGUMENTS', 'PICTIDE_UPDATE_VERIFY_TOKEN'):
        environment.pop(name, None)
    log = path.parent / 'apply.log'
    marker = path.parent.parent / 'installing.json'
    try:
        with log.open('ab') as stream:
            child = subprocess.Popen([str(program), '--apply-update', str(path)], stdin=subprocess.DEVNULL,
                                stdout=stream, stderr=subprocess.STDOUT, env=environment,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                                start_new_session=sys.platform != 'win32')
        marker.write_text(json.dumps(dict(pid=child.pid, plan=str(path))), encoding='utf8')
        return child
    except Exception:
        marker.unlink(missing_ok=True)
        raise


def copy(source, target):
    source, target = filesystem_path(source), filesystem_path(target)
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target)


def remove(path):
    path = filesystem_path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def snapshot_databases(data, backup):
    originals = []
    for source in (data / 'db').glob('*.sqlite3'):
        target = backup / 'db' / source.name
        filesystem_path(target.parent).mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as connection, closing(sqlite3.connect(str(filesystem_path(target)))) as destination:
            connection.backup(destination)
        originals.append(source.name)
    return originals


def verify_start(plan, installation):
    package = Path(installation.root) / 'Pictide.app' if installation.platform == 'darwin' else Path(installation.root)
    program = executable(package, installation.platform, service=True)
    environment = dict(os.environ, PICTIDE_UPDATE_VERIFY_TOKEN=plan['token'])
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    for name in ('PICTIDE_DESKTOP_PARENT_PIPE', 'PICTIDE_DESKTOP_STATUS', 'PICTIDE_DESKTOP_PARENT_PID', 'PICTIDE_DESKTOP_ARGUMENTS'):
        environment.pop(name, None)
    # A temporary CLI worker verifies the runtime without opening a second UI or dispatching tasks.
    args = [argument for argument in plan['restart_args'] if argument not in ('--desktop', '--desktop-worker')]
    worker = subprocess.Popen([str(program), *args, '--cli', '--no-browser'], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment,
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if worker.poll() is not None:
                raise RuntimeError('Updated runtime exited before readiness verification')
            try:
                health = local_json(plan['url'] + '/api/updates/health', token=plan['token'])
                if (health.get('version') == plan['version'] and health.get('pid') == worker.pid
                        and Path(health.get('data_directory', '')).resolve() == Path(plan['data'])):
                    return
            except (OSError, ValueError):
                pass
            time.sleep(.2)
        raise RuntimeError('Updated runtime did not become ready')
    finally:
        try:
            local_json(plan['url'] + '/api/updates/abort', method='POST', token=plan['token'])
        except (OSError, ValueError):
            pass
        try:
            worker.wait(timeout=15)
        except subprocess.TimeoutExpired:
            worker.terminate()
            worker.wait(timeout=15)


def restart(plan, installation):
    package = Path(installation.root) / 'Pictide.app' if installation.platform == 'darwin' else Path(installation.root)
    environment = dict(os.environ)
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    for name in ('PICTIDE_DESKTOP_PARENT_PIPE', 'PICTIDE_DESKTOP_STATUS', 'PICTIDE_DESKTOP_PARENT_PID', 'PICTIDE_DESKTOP_ARGUMENTS', 'PICTIDE_UPDATE_VERIFY_TOKEN'):
        environment.pop(name, None)
    arguments = [str(executable(package, installation.platform)), *plan['restart_args']]
    return subprocess.Popen(arguments, cwd=installation.root, env=environment, stdin=subprocess.DEVNULL,
                     creationflags=(subprocess.CREATE_NEW_CONSOLE if '--cli' in plan['restart_args'] else subprocess.CREATE_NO_WINDOW) if sys.platform == 'win32' else 0,
                     start_new_session=sys.platform != 'win32')


def apply_plan(path, *, verifier=verify_start, restarter=restart):
    path = Path(path).resolve()
    document = json.loads(path.read_text(encoding='utf8'))
    data = Path(document['data']).resolve()
    if not path.is_relative_to(data / 'tmp/updates'):
        raise ValueError('Invalid update plan location')
    with UpdateLease(data):
        try:
            return _apply_plan(path, verifier=verifier, restarter=restarter)
        finally:
            marker = data / 'tmp/updates/installing.json'
            if marker.exists() and json.loads(marker.read_text(encoding='utf8')).get('plan') == str(path):
                marker.unlink()


def _apply_plan(path, *, verifier, restarter):
    path = Path(path).resolve()
    plan = json.loads(path.read_text(encoding='utf8'))
    installation = Installation(**plan['installation'])
    data, root, package = Path(plan['data']).resolve(), Path(installation.root).resolve(), Path(plan['package']).resolve()
    if (plan.get('schema') != 1 or not path.is_relative_to(data / 'tmp/updates')
            or not package.is_relative_to(data / 'cache/updates') or install_reason(installation, data)):
        raise ValueError('Invalid update plan or installation directory')
    metadata = package_metadata(package, installation.platform)
    if metadata != {'schema': 1, 'version': plan['version'], 'platform': installation.platform, 'arch': installation.arch}:
        raise ValueError('Staged update no longer matches the approved plan')
    deadline = time.monotonic() + 60
    while any(alive(pid) for pid in plan['pids']):
        if time.monotonic() > deadline:
            raise RuntimeError('The previous application did not exit; no files were replaced')
        time.sleep(.1)
    if running_pids(installation):
        raise RuntimeError('Another instance is using this installation; no files were replaced')
    backup = data / 'backups/updates' / (installation.version + '-' + path.parent.name)
    names = PROGRAM_FILES[installation.platform]
    if any((root / name).resolve() == data or data.is_relative_to((root / name).resolve()) for name in names):
        raise ValueError('Application data overlaps replaceable program files')
    database_names = None
    originals, replaced = [], []
    result = data / 'tmp/updates/result.json'
    try:
        backup.mkdir(parents=True)
        database_names = snapshot_databases(data, backup)
        # Copy a complete recovery point before changing any program file.
        for name in names:
            target = root / name
            if target.exists():
                saved = backup / 'program' / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                copy(target, saved)
                originals.append(name)
        for name in names:
            target = root / name
            source = package if installation.platform == 'darwin' else package / name
            replaced.append(name)
            remove(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            copy(source, target)
        verifier(plan, installation)
        result.write_text(json.dumps({'phase': 'installed', 'version': plan['version'], 'backup': str(backup)}), encoding='utf8')
        restarter(plan, installation)
    except Exception as error:
        for name in replaced:
            remove(root / name)
            if name in originals:
                copy(backup / 'program' / name, root / name)
        if replaced and database_names is not None:
            for current in (data / 'db').glob('*.sqlite3'):
                for suffix in ('-wal', '-shm'):
                    Path(str(current) + suffix).unlink(missing_ok=True)
                if current.name not in database_names:
                    current.unlink()
            for name in database_names:
                shutil.copy2(filesystem_path(backup / 'db' / name), data / 'db' / name)
        try:
            result.write_text(json.dumps({'phase': 'rolled_back', 'version': installation.version, 'error': str(error), 'backup': str(backup)}), encoding='utf8')
        finally:
            restarter(plan, installation)
        raise
