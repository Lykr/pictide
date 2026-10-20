"""Build a native directory-style Pictide portable package."""
import argparse
from contextlib import closing
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import __version__
from backend.paths import DataPaths
from backend.recommand.resources import model_catalog
from corpus.download import sha256 as digest
from corpus.portable import prepare_resources


def export_resources(resources, seed):
    """Export the public library and metadata for the startup model download."""
    seed = Path(seed)
    library = resources.library
    target = seed / 'libraries' / library.name
    target.parent.mkdir(parents=True)
    with closing(sqlite3.connect(library.as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(target)) as db:
        source.backup(db)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        for name in tables - {'tags', 'correlations', 'dataset'}:
            db.execute('DROP TABLE "' + name.replace('"', '""') + '"')
        db.commit()
        db.execute('VACUUM')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise RuntimeError('Vocabulary integrity check failed.')
    model = model_catalog()
    manifest = {'version': __version__, 'provenance': resources.provenance,
                'model': model,
                'model_sha256': next(item['sha256'] for item in model['files'] if item['path'] == 'model.onnx'),
                'files': []}
    for path in sorted(seed.rglob('*')):
        if path.is_file():
            manifest['files'].append({'path': path.relative_to(seed).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)})
    (seed / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def copy_licenses(destination):
    """Keep licenses and versions for installed runtime dependencies."""
    from packaging.requirements import Requirement
    todo = ['aiohttp', 'fastembed', 'numpy']
    seen = set()
    versions = {}
    while todo:
        name = todo.pop()
        dist = metadata.distribution(name)
        key = dist.metadata['Name'].lower().replace('_', '-')
        if key in seen:
            continue
        seen.add(key)
        versions[key] = dist.version
        for requirement in dist.requires or []:
            item = Requirement(requirement)
            if item.marker is None or item.marker.evaluate({'extra': ''}):
                todo.append(item.name)
        for file in dist.files or []:
            if any(word in str(file).lower() for word in ('license', 'copying', 'notice')):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = destination / key / file.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    (destination / 'versions.json').write_text(json.dumps(versions, indent=2), encoding='utf-8')
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        python_license = ROOT / 'scripts/licenses/Python.txt'
    shutil.copyfile(python_license, destination / 'Python.txt')
    # MiniLM and tokenizers use Apache-2.0, whose full terms accompany the attribution.
    apache = destination / 'fastembed/LICENSE'
    shutil.copyfile(apache, destination / 'Apache-2.0.txt')
    installer = metadata.distribution('pyinstaller')
    for file in installer.files or []:
        if 'license' in str(file).lower() and Path(installer.locate_file(file)).is_file():
            target = destination / 'pyinstaller' / file.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(installer.locate_file(file), target)


def desktop_icon(directory):
    """Convert the website icon to the native desktop format."""
    from PIL import Image
    destination = Path(directory) / ('desktop.icns' if sys.platform == 'darwin' else 'desktop.ico')
    with Image.open(ROOT / 'web/public/icons/pictide-512.png') as image:
        if sys.platform == 'darwin':
            image.convert('RGBA').save(destination, format='ICNS')
        else:
            image.convert('RGBA').save(destination, format='ICO',
                                       sizes=[(size, size) for size in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    return destination


def write_archive(package, archive):
    """Use the macOS archiver for framework links and bundle metadata."""
    if sys.platform == 'darwin':
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--keepParent', str(package), str(archive)], check=True)
        return
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(package.rglob('*')):
            name = path.relative_to(package.parent).as_posix()
            if path.is_symlink():
                link = zipfile.ZipInfo(name)
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                bundle.writestr(link, os.readlink(path))
            else:
                bundle.write(path, name)


def build_frontend(destination):
    """Prepare locked dependencies and build into the isolated package workspace."""
    pnpm = shutil.which('pnpm')
    if pnpm is None:
        raise RuntimeError('Install the pnpm version specified by web/package.json before building.')
    web = ROOT / 'web'
    for arguments in (['install', '--frozen-lockfile'], ['run', 'typecheck'],
                      ['run', 'build', '--out-dir', str(destination)]):
        subprocess.run([pnpm, '--dir', str(web), *arguments], cwd=ROOT, check=True)


def build(output_dir=None, *, dataset_dir=ROOT / 'dev/datasets/danbooru-2026',
          cache_dir=ROOT / 'dev/cache/portable',
          profile=ROOT / 'corpus/profiles/compact.json', prebuilt_library=None):
    started = time.perf_counter()
    build_paths = DataPaths(ROOT / 'dev/build').configure_runtime()
    output = Path(output_dir or ROOT / 'releases').expanduser().resolve()
    name = f'pictide-{__version__}-{sys.platform}-{platform.machine().lower()}'
    archive_path = output / (name + '.zip')
    report = ROOT / 'dev/verification/portable' / name.removeprefix('pictide-') / 'build-report.json'
    result = {'passed': False, 'archive': str(archive_path), 'report': str(report)}
    try:
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='portable-build-', dir=build_paths.tmp) as temporary:
            working = Path(temporary)
            front = working / 'frontend'
            build_frontend(front)
            resources = prepare_resources(dataset_dir, cache_dir, profile,
                                          prebuilt_library=prebuilt_library,
                                          progress=lambda text: print(text, flush=True))
            runtime = working / 'native'
            runtime.mkdir(parents=True)
            seed = working / 'resources'
            manifest = export_resources(resources, seed)
            print('Resources exported; packaging the native runtime.', flush=True)
            command = [sys.executable, '-m', 'PyInstaller', '--onedir', '--noconfirm', '--name', 'Pictide',
                       '--distpath', str(runtime), '--workpath', str(working / 'work'), '--specpath', str(working),
                       '--paths', str(ROOT), '--add-data', f'{front}{os.pathsep}web/dist',
                       '--add-data', f'{ROOT / "backend/recommand/model.json"}{os.pathsep}backend/recommand',
                       '--add-data', f'{ROOT / "docs/assets/workflows/anima-turbo-v1.1.api.json"}{os.pathsep}backend/workflows',
                       '--add-data', f'{seed}{os.pathsep}resources', '--collect-all', 'fastembed',
                       '--collect-all', 'onnxruntime', '--collect-all', 'tokenizers',
                       '--copy-metadata', 'fastembed', '--copy-metadata', 'onnxruntime', '--copy-metadata', 'tokenizers',
                       '--exclude-module', 'torch', '--exclude-module', 'tensorflow', '--exclude-module', 'pytest',
                       str(ROOT / 'scripts/portable_entry.py')]
            if sys.platform == 'win32':
                icon = desktop_icon(working)
                command[-1:-1] = ['--icon', str(icon), '--add-data', f'{icon}{os.pathsep}backend',
                                  '--exclude-module', 'tkinter', '--exclude-module', 'PySide6',
                                  '--exclude-module', 'PyQt6', '--exclude-module', 'PyQt5',
                                  '--exclude-module', 'wx']
            elif sys.platform == 'darwin':
                command[-1:-1] = ['--windowed', '--icon', str(desktop_icon(working)),
                                  '--osx-bundle-identifier', 'org.pictide.Pictide',
                                  '--exclude-module', 'tkinter', '--exclude-module', 'PySide6',
                                  '--exclude-module', 'PyQt6', '--exclude-module', 'PyQt5', '--exclude-module', 'wx']
            subprocess.run(command, cwd=ROOT, check=True)
            bundled = runtime / 'Pictide'
            if sys.platform == 'win32':
                package = bundled
                documents = package
                launcher_name = 'Pictide.exe'
                desktop_help = ('Startup progress appears while preparing dependencies, then Pictide stays in the system tray.\n'
                                'Use the tray menu to reopen Pictide, view logs or exit. Closing the browser keeps Pictide running.\n'
                                'Run Pictide.exe --cli to use terminal mode; press Ctrl+C to stop.\n'
                                'First launch confirms your data folder (default: data/ beside Pictide.exe) and remembers it.\n'
                                'Run Pictide.exe --setup to choose again; existing data stays in its previous folder.\n')
            elif sys.platform == 'darwin':
                package = runtime / 'Pictide.app'
                documents = package / 'Contents/Resources'
                native = package / 'Contents/MacOS'
                info_path = package / 'Contents/Info.plist'
                with info_path.open('rb') as handle:
                    info = plistlib.load(handle)
                info.update(LSUIElement=True, NSHighResolutionCapable=True,
                            CFBundleShortVersionString=__version__, CFBundleVersion=__version__)
                info['NSAppTransportSecurity'] = {'NSAllowsLocalNetworking': True}
                with info_path.open('wb') as handle:
                    plistlib.dump(info, handle)
                (native / 'Pictide').rename(native / 'PictideService')
                subprocess.run(['/usr/bin/xcrun', 'swiftc', str(ROOT / 'scripts/macos_launcher.swift'),
                                '-o', str(native / 'Pictide'), '-framework', 'AppKit'], cwd=ROOT, check=True)
                shutil.copyfile(ROOT / 'web/public/icons/pictide-512.png', documents / 'desktop.png')
                launcher_name = 'Pictide.app'
                desktop_help = ('Drag Pictide.app into Applications and open it.\n'
                                'The menu bar shows startup status and provides Open Pictide, View Logs and Quit.\n'
                                'Closing the browser keeps Pictide running.\n'
                                'Data stays in ~/Library/Application Support/Pictide/.\n'
                                'This app is ad-hoc signed and not notarized; macOS may require permission in Privacy & Security on first launch.\n')
            else:
                package = working / 'Pictide'
                documents = package
                target = package / 'data/runtime/pictide'
                target.parent.mkdir(parents=True)
                bundled.rename(target)
                launcher = package / 'start.sh'
                launcher.write_text('#!/bin/sh\nroot=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$root/data/runtime/pictide/Pictide" "$@"\n', encoding='utf-8')
                launcher.chmod(0o755)
                launcher_name = launcher.name
                desktop_help = 'Close the launcher window or press Ctrl+C to stop.\nData stays in data/.\n'
            (documents / 'README.txt').write_text('Pictide\n\nRun ' + launcher_name + ' to open Pictide.\nThe first launch downloads and verifies the MiniLM recommendation dependency before opening the app.\nAn internet connection is required until this download completes.\nLater launches reuse the verified dependency in the data directory.\nConfigure an image API in Settings.\n' + desktop_help + 'Use --port, --data-dir, --lan or --no-browser when needed.\n', encoding='utf-8')
            for name in ('LICENSE', 'NOTICE'):
                shutil.copyfile(ROOT / name, documents / name)
            notices = documents / 'licenses'
            notices.mkdir()
            copy_licenses(notices)
            shutil.copyfile(ROOT / 'web/src/THIRD_PARTY_NOTICES.md', notices / 'frontend.md')
            (notices / 'MiniLM.txt').write_text('Model: sentence-transformers/all-MiniLM-L6-v2\nONNX export: Qdrant/all-MiniLM-L6-v2-onnx\nLicense: Apache-2.0\nONNX SHA-256: ' + manifest['model_sha256'] + '\nhttps://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx\n', encoding='utf-8')
            if sys.platform == 'darwin':
                # PyInstaller signs its libraries; only the replacement launcher and outer bundle change.
                for target in (package / 'Contents/MacOS/Pictide', package):
                    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(target)], check=True)
                subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(package)], check=True)
            archive = working / f'pictide-{__version__}-{sys.platform}-{platform.machine().lower()}.zip'
            write_archive(package, archive)
            result.update({'archive_bytes': archive.stat().st_size,
                           'unpacked_bytes': sum(p.stat().st_size for p in package.rglob('*') if p.is_file()),
                           'resources': manifest['provenance']})
            if sys.platform in {'win32', 'darwin'}:
                gui_files = [path.relative_to(package).as_posix() for path in package.rglob('*')
                             if path.name.lower() in {'tcl', 'tk', '_tkinter.pyd', 'pyside6', 'pyqt6', 'pyqt5', 'wx'}
                             or path.name.lower().startswith(('tcl86', 'tk86', 'qt6core', 'qt5core'))]
                if gui_files:
                    raise RuntimeError('Unexpected GUI runtime in portable package: ' + ', '.join(gui_files))
                icon_path = (package / '_internal/backend/desktop.ico' if sys.platform == 'win32'
                             else package / 'Contents/Resources/desktop.png')
                result['desktop'] = {'mode': ('native Windows tray with temporary startup console' if sys.platform == 'win32'
                                              else 'native macOS AppKit preparation window and menu bar'),
                                     'icon_source': 'web/public/icons/pictide-512.png',
                                     'icon_bytes': icon_path.stat().st_size,
                                     'extra_gui_runtime_files': gui_files}
            # Publish only the complete archive; existing local versions remain usable on failure.
            with tempfile.NamedTemporaryFile(prefix='.', suffix='.zip.part', dir=output, delete=False) as handle:
                partial_archive = Path(handle.name)
            try:
                shutil.copyfile(archive, partial_archive)
                os.replace(partial_archive, archive_path)
            finally:
                partial_archive.unlink(missing_ok=True)
            result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        result['build_seconds'] = round(time.perf_counter() - started, 2)
        report.parent.mkdir(parents=True, exist_ok=True)
        partial = report.with_suffix('.json.part')
        partial.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        os.replace(partial, report)
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir', type=Path, default=ROOT / 'dev/datasets/danbooru-2026',
                        help='Persistent raw dataset and download manifest directory')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'dev/cache/portable',
                        help='Rebuildable vocabulary cache directory')
    parser.add_argument('--profile', type=Path, default=ROOT / 'corpus/profiles/compact.json',
                        help='Vocabulary processing profile')
    parser.add_argument('--prebuilt-library', type=Path,
                        help='Directory containing the locked vocabulary.sqlite3 and report.json; never rebuilds raw data')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'releases',
                        help='Final archive directory (default: releases/); local same-name builds are replaced atomically.')
    options = parser.parse_args()
    build(options.output_dir, dataset_dir=options.dataset_dir, cache_dir=options.cache_dir,
          profile=options.profile, prebuilt_library=options.prebuilt_library)
