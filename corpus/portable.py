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
DEFAULT_PREBUILT_LOCK = Path(__file__).with_name('prebuilt.json')


@dataclass(frozen=True)
class PreparedResources:
    library: Path
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


def vocabulary_inputs(profile, lock_path=DEFAULT_LOCK):
    lock = json.loads(Path(lock_path).read_text(encoding='utf-8'))
    options = importer.processing_options(json.loads(Path(profile).read_text(encoding='utf-8-sig')))
    return dict(dataset=lock['dataset'], options=options,
                processor_sha256=download.sha256(Path(importer.__file__)))


def prepare_vocabulary(dataset_dir, cache_dir, profile, *, lock_path=DEFAULT_LOCK, progress=print):
    """Build or reuse a release vocabulary without application/model dependencies."""
    dataset_dir = Path(dataset_dir).expanduser().resolve()
    cache_dir = Path(cache_dir).expanduser().resolve()
    if dataset_dir.is_relative_to(cache_dir) or cache_dir.is_relative_to(dataset_dir):
        raise ValueError('Dataset and build cache must use separate directory trees')
    inputs = vocabulary_inputs(profile, lock_path)
    dataset, options = inputs['dataset'], inputs['options']
    identity = dict(**inputs,
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
    return library, report


def load_prebuilt(directory, profile, *, lock_path=DEFAULT_LOCK,
                  prebuilt_lock_path=DEFAULT_PREBUILT_LOCK):
    """Verify a locked release artifact; never import processing dependencies."""
    directory = Path(directory).expanduser().resolve()
    locked = json.loads(Path(prebuilt_lock_path).read_text(encoding='utf-8'))
    files = {item['path']: item for item in locked['files']}
    if len(locked['files']) != 2 or set(files) != {'vocabulary.sqlite3', 'report.json'}:
        raise ValueError('Prebuilt lock must describe vocabulary.sqlite3 and report.json')
    for name, item in files.items():
        if not download.verified(directory / name, item):
            raise ValueError(f'Prebuilt vocabulary failed verification: {name}; prepare and publish the resource again')
    report = json.loads((directory / 'report.json').read_text(encoding='utf-8'))
    identity = report['identity']
    if any(identity.get(key) != value for key, value in vocabulary_inputs(profile, lock_path).items()):
        raise ValueError('Prebuilt vocabulary is stale for this source/profile; prepare and publish a new resource')
    key = fingerprint(identity)
    if (report['fingerprint'] != key or locked['fingerprint'] != key
            or locked['release_tag'] != 'corpus-' + key or report['file'] != files['vocabulary.sqlite3']):
        raise ValueError('Prebuilt vocabulary manifest does not match its resource lock')
    library = directory / 'vocabulary.sqlite3'
    if not cached_library(library, directory / 'report.json', identity):
        raise ValueError('Prebuilt vocabulary database failed integrity/readiness verification')
    return library, report


def prepare_resources(dataset_dir, cache_dir, profile, *,
                      lock_path=DEFAULT_LOCK, prebuilt_library=None,
                      prebuilt_lock_path=DEFAULT_PREBUILT_LOCK, progress=print):
    if os.environ.get('GITHUB_ACTIONS') == 'true' and prebuilt_library is None:
        raise ValueError('GitHub Actions builds require --prebuilt-library; prepare the resource locally')
    if prebuilt_library is not None:
        library, report = load_prebuilt(prebuilt_library, profile, lock_path=lock_path,
                                        prebuilt_lock_path=prebuilt_lock_path)
        progress(f'Prebuilt vocabulary verified: {report["fingerprint"]}')
    else:
        library, report = prepare_vocabulary(dataset_dir, cache_dir, profile,
                                             lock_path=lock_path, progress=progress)
    progress(f'Resources ready: vocabulary {report["fingerprint"]}')
    return PreparedResources(library, dict(library=report))
