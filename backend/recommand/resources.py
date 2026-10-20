"""Prepare the pinned MiniLM files before the application starts listening."""
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import time
from urllib.request import Request

from ..desktop_text import translate
from ..network import open_url as urlopen


def model_catalog():
    return json.loads(Path(__file__).with_name('model.json').read_text(encoding='utf-8'))


def _progress(message):
    print(message, flush=True)
    logging.getLogger('backend').info(message)


def _verified(path, item):
    if not path.is_file() or path.stat().st_size != item['bytes']:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest() == item['sha256']


def _download(path, item, url, progress):
    partial = path.with_suffix(path.suffix + '.part')
    for attempt in range(3):
        try:
            if partial.exists() and partial.stat().st_size >= item['bytes']:
                if not _verified(partial, item):
                    partial.unlink()
            if not _verified(partial, item):
                offset = partial.stat().st_size if partial.exists() else 0
                headers = {'User-Agent': 'Pictide model preparation'}
                if offset:
                    headers['Range'] = f'bytes={offset}-'
                with urlopen(Request(url, headers=headers), timeout=30) as stream:
                    append = bool(offset and stream.status == 206)
                    if append and not stream.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                        raise ValueError('Unexpected model download range')
                    received = offset if append else 0
                    next_progress = received
                    with partial.open('ab' if append else 'wb') as output:
                        while chunk := stream.read(256 * 1024):
                            output.write(chunk)
                            received += len(chunk)
                            if received >= next_progress:
                                progress(translate('model_progress', path=item['path'],
                                                   percent=min(100, received * 100 // item['bytes']),
                                                   received=received, total=item['bytes']))
                                next_progress = received + max(1024 * 1024, item['bytes'] // 10)
                if not _verified(partial, item):
                    raise ValueError('Model download failed size/SHA-256 verification: ' + item['path'])
            # Preserve an existing invalid or user-modified file until its replacement is verified.
            if path.exists():
                backup = path.with_name(path.name + f'.before-download-{time.time_ns()}.bak')
                shutil.copy2(path, backup)
                progress(translate('model_preserved', path=backup))
            os.replace(partial, path)
            progress(translate('model_verified', path=item['path']))
            return
        except (OSError, ValueError) as error:
            if attempt == 2:
                raise RuntimeError(translate('model_failed', path=item['path'], error=error)) from error
            progress(translate('model_retry', attempt=attempt + 1, path=item['path'], error=error))
            time.sleep(1)


def prepare_model(directory, *, catalog=None, progress=_progress):
    """Return only after every pinned file is ready; keep partials on failure."""
    directory = Path(directory).expanduser().resolve()
    catalog = model_catalog() if catalog is None else catalog
    directory.mkdir(parents=True, exist_ok=True)
    progress(translate('preparing_model', directory=directory))
    for item in catalog['files']:
        path = (directory / item['path']).resolve()
        if not path.is_relative_to(directory) or path == directory:
            raise ValueError(translate('invalid_model_path'))
        if _verified(path, item):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        url = (f'https://huggingface.co/{catalog["source"]}/resolve/{catalog["revision"]}/'
               f'{item["path"]}?download=true')
        progress(translate('downloading_model', path=item['path']))
        _download(path, item, url, progress)
    progress(translate('model_ready'))
    return directory
