"""Build a native directory-style Pictide portable package."""
import argparse
from contextlib import closing
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import __version__
from backend.paths import DataPaths
from backend.recommand.encoder import MiniLMEncoder
from corpus.download import sha256 as digest
from corpus.portable import prepare_resources


def export_resources(resources, seed):
    """Export only the prepared public library and fixed encoder snapshot."""
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
    encoder = MiniLMEncoder(resources.model_dir)
    directory, files = encoder._files()
    model_target = seed / 'models/minilm'
    model_target.mkdir(parents=True)
    for source in files:
        shutil.copyfile(source, model_target / source.name)
    manifest = {'version': __version__, 'provenance': resources.provenance,
                'model_sha256': digest(directory / 'model.onnx'), 'files': []}
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


def build(output_dir, *, dataset_dir=ROOT / 'dev/datasets/danbooru-2026',
          cache_dir=ROOT / 'dev/cache/portable', models_dir=ROOT / 'dev/models',
          profile=ROOT / 'corpus/profiles/compact.json'):
    started = time.perf_counter()
    build_paths = DataPaths(ROOT / 'dev/build').configure_runtime()
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise RuntimeError('Choose a new output directory: ' + str(output))
    front = ROOT / 'web/dist'
    if not (front / 'index.html').is_file():
        raise RuntimeError('Build the frontend before packaging.')
    resources = prepare_resources(dataset_dir, cache_dir, profile, models_dir=models_dir,
                                  progress=lambda text: print(text, flush=True))
    output.mkdir(parents=True)
    package = output / 'Pictide'
    runtime = package / 'data/runtime'
    runtime.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='portable-build-', dir=build_paths.tmp) as working:
        working = Path(working)
        seed = working / 'resources'
        manifest = export_resources(resources, seed)
        print('Resources exported; packaging the native runtime.', flush=True)
        command = [sys.executable, '-m', 'PyInstaller', '--onedir', '--noconfirm', '--name', 'Pictide',
                   '--distpath', str(runtime), '--workpath', str(working / 'work'), '--specpath', str(working),
                   '--paths', str(ROOT), '--add-data', f'{front}{os.pathsep}web/dist',
                   '--add-data', f'{seed}{os.pathsep}resources', '--collect-all', 'fastembed',
                   '--collect-all', 'onnxruntime', '--collect-all', 'tokenizers',
                   '--copy-metadata', 'fastembed', '--copy-metadata', 'onnxruntime', '--copy-metadata', 'tokenizers',
                   '--exclude-module', 'torch', '--exclude-module', 'tensorflow', '--exclude-module', 'pytest',
                   str(ROOT / 'scripts/portable_entry.py')]
        subprocess.run(command, cwd=ROOT, check=True)
    # Native bundle name is stable across systems; launcher paths are platform-specific.
    bundled = runtime / 'Pictide'
    bundled.rename(runtime / 'pictide')
    if sys.platform == 'win32':
        launcher = package / 'start.cmd'
        launcher.write_bytes(b'@echo off\r\n"%~dp0data\\runtime\\pictide\\Pictide.exe" %*\r\nif errorlevel 1 pause\r\n')
    else:
        launcher = package / ('start.command' if sys.platform == 'darwin' else 'start.sh')
        launcher.write_text('#!/bin/sh\nroot=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$root/data/runtime/pictide/Pictide" "$@"\n', encoding='utf-8')
        launcher.chmod(0o755)
    (package / 'README.txt').write_text('Pictide\n\nRun ' + launcher.name + ' to open Pictide.\nConfigure an image API in Settings.\nClose the launcher window or press Ctrl+C to stop.\nData stays in data/.\nUse --port, --data-dir, --lan or --no-browser when needed.\n', encoding='utf-8')
    notices = package / 'licenses'
    notices.mkdir()
    copy_licenses(notices)
    shutil.copyfile(ROOT / 'web/src/THIRD_PARTY_NOTICES.md', notices / 'frontend.md')
    (notices / 'MiniLM.txt').write_text('Model: sentence-transformers/all-MiniLM-L6-v2\nONNX export: Qdrant/all-MiniLM-L6-v2-onnx\nLicense: Apache-2.0\nONNX SHA-256: ' + manifest['model_sha256'] + '\nhttps://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx\n', encoding='utf-8')
    archive = output / f'pictide-{__version__}-{sys.platform}-{platform.machine().lower()}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zip:
        for path in sorted(package.rglob('*')):
            if path.is_file():
                zip.write(path, path.relative_to(output))
    result = {'directory': str(package), 'archive': str(archive), 'archive_bytes': archive.stat().st_size,
              'unpacked_bytes': sum(p.stat().st_size for p in package.rglob('*') if p.is_file()),
              'build_seconds': round(time.perf_counter() - started, 2),
              'resources': manifest['provenance']}
    (output / 'build-report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir', type=Path, default=ROOT / 'dev/datasets/danbooru-2026',
                        help='Persistent raw dataset and download manifest directory')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'dev/cache/portable',
                        help='Rebuildable vocabulary cache directory')
    parser.add_argument('--models-dir', type=Path, default=ROOT / 'dev/models',
                        help='Persistent pinned recommendation model directory')
    parser.add_argument('--profile', type=Path, default=ROOT / 'corpus/profiles/compact.json',
                        help='Vocabulary processing profile')
    parser.add_argument('--output-dir', default=ROOT / 'releases' / f'pictide-{__version__}-{sys.platform}-{time.strftime("%Y%m%d-%H%M%S")}',
                        help='New release directory (default: releases/<version-platform-time>).')
    options = parser.parse_args()
    build(options.output_dir, dataset_dir=options.dataset_dir, cache_dir=options.cache_dir,
          models_dir=options.models_dir, profile=options.profile)
