"""Prepare pinned public resources independently of application runtime data."""
from contextlib import closing
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sqlite3

from . import download, importer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = Path(__file__).with_name('resources.json')


@dataclass(frozen=True)
class PreparedResources:
    library: Path
    model_dir: Path
    provenance: dict


def fingerprint(document):
    encoded = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def write_report(path, document):
    partial = path.with_suffix('.json.part')
    partial.write_text(json.dumps(document, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(partial, path)


def cached_library(library, report_path, identity):
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if report['identity'] != identity or not download.verified(library, report['file']):
            return None
        with closing(sqlite3.connect(library.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                return None
            if db.execute('SELECT status FROM dataset WHERE id=1').fetchone() != ('ready',):
                return None
        return report
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        return None


def prepare_resources(dataset_dir, cache_dir, profile, *, models_dir=ROOT / 'dev/models',
                      lock_path=DEFAULT_LOCK, progress=print):
    dataset_dir = Path(dataset_dir).expanduser().resolve()
    cache_dir = Path(cache_dir).expanduser().resolve()
    models_dir = Path(models_dir).expanduser().resolve()
    # Raw inputs and reusable models must survive removal of the build cache.
    if any(path.is_relative_to(cache_dir) or cache_dir.is_relative_to(path)
           for path in (dataset_dir, models_dir)):
        raise ValueError('Dataset, models and build cache must use separate directory trees')
    lock = json.loads(Path(lock_path).read_text(encoding='utf-8'))
    options = importer.processing_options(json.loads(Path(profile).read_text(encoding='utf-8-sig')))
    dataset = lock['dataset']
    identity = dict(dataset=dataset, options=options,
                    processor_sha256=download.sha256(Path(importer.__file__)),
                    dependencies={name: version(name) for name in ('numpy', 'scipy', 'pyarrow')})
    key = fingerprint(identity)
    directory = cache_dir / 'libraries' / key
    library = directory / 'vocabulary.sqlite3'
    report_path = directory / 'report.json'
    report = cached_library(library, report_path, identity)
    if report:
        progress(f'Vocabulary cache hit: {key}')
    else:
        progress(f'Preparing vocabulary: {key}')
        download.download(dataset_dir, source=dataset['source'], revision=dataset['revision'],
                          files=dataset['files'], progress=progress)
        directory.mkdir(parents=True, exist_ok=True)
        partial = directory / 'vocabulary.build.sqlite3'
        # Only the incomplete output is replaced; the resumable statistics stay.
        partial.unlink(missing_ok=True)
        inputs = [download.resource_path(dataset_dir / 'raw', item['path']) for item in dataset['files']]
        summary = importer.import_parquet(inputs, partial, state_path=directory / 'state.sqlite3',
                                         source=dataset['source'], revision=dataset['revision'],
                                         **options, progress=progress)
        os.replace(partial, library)
        report = dict(identity=identity, fingerprint=key, statistics=summary,
                      file=dict(path=library.name, bytes=library.stat().st_size,
                                sha256=download.sha256(library)))
        write_report(report_path, report)
    model = lock['model']
    snapshot = download.resource_path(models_dir / 'minilm', model['revision'])
    for item in model['files']:
        path = download.resource_path(snapshot, item['path'])
        if not download.verified(path, item):
            progress(f'Downloading MiniLM: {item["path"]}')
            url = f'https://huggingface.co/{model["source"]}/resolve/{model["revision"]}/{item["path"]}?download=true'
            download.download_file(url, path, item, replace_invalid=True)
    progress(f'Resources ready: vocabulary {key}, MiniLM {model["revision"]}')
    return PreparedResources(library, snapshot, dict(library=report, model=model))
