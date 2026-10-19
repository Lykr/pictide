"""Prepare the pinned MiniLM files before the application starts listening."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from urllib.request import Request, urlopen


def model_catalog():
    return json.loads(Path(__file__).with_name('model.json').read_text(encoding='utf-8'))


def _progress(message):
    print(message, flush=True)


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
                                progress(f'MiniLM {item["path"]}: {min(100, received * 100 // item["bytes"])}% '
                                         f'({received:,}/{item["bytes"]:,} bytes)')
                                next_progress = received + max(1024 * 1024, item['bytes'] // 10)
                if not _verified(partial, item):
                    raise ValueError('Model download failed size/SHA-256 verification: ' + item['path'])
            # Preserve an existing invalid or user-modified file until its replacement is verified.
            if path.exists():
                backup = path.with_name(path.name + f'.before-download-{time.time_ns()}.bak')
                shutil.copy2(path, backup)
                progress('Previous model file preserved: ' + str(backup))
            os.replace(partial, path)
            progress('MiniLM verified: ' + item['path'])
            return
        except (OSError, ValueError) as error:
            if attempt == 2:
                raise RuntimeError(f'Cannot prepare MiniLM {item["path"]}: {error}. '
                                   'Check the connection and restart to resume the download.') from error
            progress(f'MiniLM download retry {attempt + 1}/2: {item["path"]} ({error})')
            time.sleep(1)


def prepare_model(directory, *, catalog=None, progress=_progress):
    """Return only after every pinned file is ready; keep partials on failure."""
    directory = Path(directory).expanduser().resolve()
    catalog = model_catalog() if catalog is None else catalog
    directory.mkdir(parents=True, exist_ok=True)
    progress('Preparing MiniLM before starting Pictide: ' + str(directory))
    for item in catalog['files']:
        path = (directory / item['path']).resolve()
        if not path.is_relative_to(directory) or path == directory:
            raise ValueError('Model files must remain inside the selected model directory')
        if _verified(path, item):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        url = (f'https://huggingface.co/{catalog["source"]}/resolve/{catalog["revision"]}/'
               f'{item["path"]}?download=true')
        progress('Downloading MiniLM: ' + item['path'])
        _download(path, item, url, progress)
    progress('MiniLM ready. Starting Pictide.')
    return directory
