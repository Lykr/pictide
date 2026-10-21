"""Detect the native package and validate staged archives without touching user data."""
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import zipfile

from .contracts import Installation, PROGRAM_FILES
from .files import filesystem_path


def detect_installation():
    if not getattr(sys, 'frozen', False):
        return None
    metadata = Path(sys._MEIPASS) / 'resources/installation.json'
    if not metadata.is_file():
        return None
    info = json.loads(metadata.read_text(encoding='utf8'))
    if info.get('schema') != 1 or info.get('platform') != sys.platform or sys.platform not in PROGRAM_FILES:
        return None
    executable = Path(sys.executable).resolve()
    root = executable.parents[3] if sys.platform == 'linux' else executable.parents[2].parent if sys.platform == 'darwin' else executable.parent
    expected = (root / 'Pictide.app/Contents/MacOS/PictideService' if sys.platform == 'darwin'
                else root / ('Pictide.exe' if sys.platform == 'win32' else 'data/runtime/pictide/Pictide'))
    if executable != expected.resolve():
        return None
    return Installation(str(root), sys.platform, info['arch'], info['version'])


def install_reason(installation, data):
    if installation is None:
        return 'manual_installation' if getattr(sys, 'frozen', False) else 'source_installation'
    root = Path(installation.root).resolve()
    if not os.access(root, os.W_OK):
        return 'directory_read_only'
    for name in PROGRAM_FILES[installation.platform]:
        target = root / name
        if Path(data).resolve().is_relative_to(target.resolve()):
            return 'data_inside_program'
        if target.is_symlink():
            return 'linked_installation'
    return ''


def package_metadata(package, system):
    candidates = (package / '_internal/resources/installation.json', package / 'data/runtime/pictide/_internal/resources/installation.json')
    if system == 'darwin':
        candidates = (package / 'Contents/Resources/resources/installation.json', package / 'Contents/Frameworks/resources/installation.json')
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding='utf8'))
    raise ValueError('The update package has no installation metadata')


def executable(package, system, *, service=False):
    if system == 'darwin':
        return package / 'Contents/MacOS' / ('PictideService' if service else 'Pictide')
    return package / ('data/runtime/pictide/Pictide' if system == 'linux' else 'Pictide.exe')


def extract_package(archive, destination, release, installation):
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(filesystem_path(destination))
    destination.mkdir(parents=True)
    name = 'Pictide.app' if installation.platform == 'darwin' else 'Pictide'
    links = []
    with zipfile.ZipFile(archive) as bundle:
        total = 0
        for item in bundle.infolist():
            path = PurePosixPath(item.filename)
            metadata_entry = (installation.platform == 'darwin' and path.parts and path.parts[0] == '__MACOSX'
                              and (len(path.parts) == 1 or path.parts[1] in (name, '._' + name)))
            if (not path.parts or path.parts[0] != name and not metadata_entry or path.is_absolute() or '..' in path.parts
                    or '\\' in item.filename or ':' in item.filename):
                raise ValueError('Unexpected path in update archive')
            total += item.file_size
            if total > release.asset['unpacked_bytes']:
                raise ValueError('Update archive exceeds its declared unpacked size')
            if metadata_entry:
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError('Unexpected metadata symlink in update archive')
                continue  # ditto restores AppleDouble metadata, rather than treating it as program files.
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                target = os.fsdecode(bundle.read(item))
                output = destination / item.filename
                if installation.platform == 'win32' or os.path.isabs(target) or not (output.parent / target).resolve().is_relative_to(destination / name):
                    raise ValueError('Unsafe symlink in update archive')
                links.append((output, target))
            elif installation.platform != 'darwin':
                bundle.extract(item, filesystem_path(destination))
                if mode & 0o777:
                    filesystem_path(destination / item.filename).chmod(mode & 0o777)
        if installation.platform == 'darwin':
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(archive), str(destination)], check=True)
        else:
            for path, target in links:
                path.symlink_to(target)
    package = destination / name
    filesystem_package = filesystem_path(package)
    for path in filesystem_package.rglob('*'):
        if path.is_symlink() and (not path.exists() or not path.resolve().is_relative_to(filesystem_package)):
            raise ValueError('Broken or external symlink in update package')
    metadata = package_metadata(package, installation.platform)
    if metadata != {'schema': 1, 'version': release.version, 'platform': installation.platform, 'arch': installation.arch}:
        raise ValueError('Update package version or platform does not match the release')
    for relative in PROGRAM_FILES[installation.platform] if installation.platform != 'darwin' else ('Contents',):
        if not (package / relative).exists():
            raise ValueError('Incomplete update package: ' + relative)
    if not executable(package, installation.platform, service=True).is_file():
        raise ValueError('Missing update executable')
    if installation.platform == 'darwin':
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(package)], check=True)
    return package
