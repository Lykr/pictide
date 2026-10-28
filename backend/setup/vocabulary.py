"""Choose and download a pinned vocabulary before composing application services."""
import hashlib
import json
import logging
from pathlib import Path
import time
from urllib.request import Request

from ..desktop.text import translate
from ..network import open_url as urlopen
from ..store.candidate_libraries import CandidateLibraries

EDITIONS = ('filtered', 'all-ratings')


def vocabulary_catalog():
    return json.loads(Path(__file__).with_name('vocabularies.json').read_text(encoding='utf-8'))


def _progress(message):
    print(message, flush=True)
    logging.getLogger('backend').info(message)


def choose_vocabulary(paths, requested=None, *, interactive=False, progress=_progress, read=None):
    """Keep any valid installed library; otherwise use an explicit or interactive choice."""
    if requested is not None and requested not in EDITIONS:
        raise ValueError('Unknown vocabulary edition')
    libraries = CandidateLibraries(paths)
    if libraries.listing()['libraries']:
        libraries.selected_path()
        return None
    if requested is not None or not interactive:
        return requested or 'filtered'
    progress(translate('vocabulary_choose'))
    progress(translate('vocabulary_filtered'))
    progress(translate('vocabulary_all_ratings'))
    while True:
        try:
            choice = (read or input)(translate('vocabulary_choice')).strip()
        except EOFError:
            return 'filtered'
        if choice in ('', '1', 'filtered'):
            return 'filtered'
        if choice in ('2', 'all-ratings'):
            return 'all-ratings'
        progress(translate('vocabulary_invalid_choice'))


def _verified(path, item):
    if not path.is_file() or path.stat().st_size != item['bytes']:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest() == item['sha256']


def prepare_vocabulary(paths, requested=None, *, interactive=False, progress=_progress):
    edition = choose_vocabulary(paths, requested, interactive=interactive, progress=progress)
    if edition is None:
        return
    catalog = vocabulary_catalog()
    item = catalog['editions'][edition]['file']
    directory = paths.cache / 'downloads' / 'vocabularies' / item['sha256']
    directory.mkdir(parents=True, exist_ok=True)
    partial = directory / (item['path'] + '.part')
    url = f'https://github.com/Lykr/pictide/releases/download/{catalog["release_tag"]}/{item["path"]}'
    if edition == 'all-ratings':
        progress(translate('vocabulary_explicit_warning'))
    progress(translate('vocabulary_downloading', edition=edition))
    for attempt in range(3):
        try:
            if partial.exists() and partial.stat().st_size >= item['bytes'] and not _verified(partial, item):
                partial.unlink()
            if not _verified(partial, item):
                offset = partial.stat().st_size if partial.exists() else 0
                headers = {'User-Agent': 'Pictide vocabulary preparation'}
                if offset:
                    headers['Range'] = f'bytes={offset}-'
                with urlopen(Request(url, headers=headers), timeout=30) as stream:
                    append = bool(offset and stream.status == 206)
                    if append and not stream.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                        raise ValueError('Unexpected vocabulary download range')
                    received = offset if append else 0
                    next_progress = received
                    with partial.open('ab' if append else 'wb') as output:
                        while chunk := stream.read(256 * 1024):
                            if received + len(chunk) > item['bytes']:
                                raise ValueError('Vocabulary download exceeds its expected size')
                            output.write(chunk)
                            received += len(chunk)
                            if received >= next_progress:
                                progress(translate('vocabulary_progress', edition=edition,
                                                   percent=min(100, received * 100 // item['bytes']),
                                                   received=received, total=item['bytes']))
                                next_progress = received + max(1024 * 1024, item['bytes'] // 10)
            if not _verified(partial, item):
                raise ValueError('Vocabulary download failed size/SHA-256 verification')
            libraries = CandidateLibraries(paths)
            record = libraries.add(partial, item['path'])
            libraries.select(record['filename'])
            partial.unlink()
            progress(translate('vocabulary_ready', filename=record['filename']))
            return
        except (OSError, ValueError) as error:
            if attempt == 2:
                raise RuntimeError(translate('vocabulary_failed', edition=edition, error=error)) from error
            progress(translate('vocabulary_retry', attempt=attempt + 1, edition=edition, error=error))
            time.sleep(1)
