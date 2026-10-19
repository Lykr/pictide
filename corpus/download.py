"""Download every Parquet shard, pinning revision and verifying SHA-256.

Only metadata files are downloaded. The download manifest is SQLite and the
original Parquet files remain available for repeatable offline processing.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import hashlib
import json
import os
import sqlite3
import time
import urllib.request

SOURCE = 'Shio-Koube/Danbooru-2026-parquet-metadata'


def response(url, headers=None):
    request = urllib.request.Request(url, headers={'User-Agent': 'Pictide metadata importer', **(headers or {})})
    return urllib.request.urlopen(request, timeout=60)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(2 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def resource_path(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Resource path must stay inside its destination")
    return path


def verified(path, item):
    return path.is_file() and path.stat().st_size == item['bytes'] and sha256(path) == item['sha256']


def download_file(url, path, item, *, replace_invalid=False):
    """Verify an existing file, or resume a download and publish it atomically."""
    path = Path(path)
    if verified(path, item):
        return
    if path.exists() and not replace_invalid:
        raise ValueError(f'Existing file failed verification: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + '.part')
    for attempt in range(4):
        try:
            if partial.exists() and partial.stat().st_size >= item['bytes']:
                if verified(partial, item):
                    os.replace(partial, path)
                    return
                partial.unlink()
            offset = partial.stat().st_size if partial.exists() else 0
            with response(url, {'Range': f'bytes={offset}-'} if offset else {}) as stream:
                append = bool(offset and stream.status == 206)
                if append and not stream.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise ValueError('Unexpected download range')
                with partial.open('ab' if append else 'wb') as output:
                    while chunk := stream.read(2 * 1024 * 1024):
                        output.write(chunk)
            if not verified(partial, item):
                raise ValueError(f'Download failed verification: {item["path"]}')
            os.replace(partial, path)
            return
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2)


def download(destination, *, source=SOURCE, revision=None, files=None, progress=print):
    """A pinned file catalog permits offline reuse without querying the Hub."""
    destination = Path(destination).resolve()
    raw = destination / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    if revision is None:
        with response('https://huggingface.co/api/datasets/' + source) as stream:
            revision = json.load(stream)['sha']
    if files is None:
        with response(f'https://huggingface.co/api/datasets/{source}/tree/{revision}?recursive=true&expand=false') as stream:
            files = [dict(path=item['path'], bytes=item['size'], sha256=item['lfs']['oid'])
                     for item in json.load(stream) if item['path'].endswith('.parquet')]
    if not files:
        raise ValueError('No Parquet files in the dataset catalog')
    for item in files:
        resource_path(raw, item['path'])
    # Reject unlisted shards: the importer must consume exactly the pinned snapshot.
    listed = {resource_path(raw, item['path']) for item in files}
    if set(raw.rglob('*.parquet')) - listed:
        raise ValueError('Dataset contains unlisted Parquet files; use a separate dataset directory')
    db = sqlite3.connect(destination / 'download.sqlite3')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS files (name TEXT PRIMARY KEY, revision TEXT, size INTEGER, sha256 TEXT, completed INTEGER NOT NULL DEFAULT 0)')
        recorded = db.execute('SELECT name,revision,size,sha256 FROM files').fetchall()
        expected = {(item['path'], revision, item['bytes'], item['sha256']) for item in files}
        if recorded and not set(recorded) <= expected:
            raise ValueError('Dataset manifest belongs to another revision or catalog; choose another dataset directory')
        db.executemany('INSERT OR IGNORE INTO files(name,revision,size,sha256) VALUES(?,?,?,?)', sorted(expected))
        db.commit()
        progress(f'{source}@{revision}: {len(files)} shards, {sum(item["bytes"] for item in files):,} bytes')

        def one(item):
            path = resource_path(raw, item['path'])
            url = f'https://huggingface.co/datasets/{source}/resolve/{revision}/{item["path"]}?download=true'
            download_file(url, path, item)
            return item['path']

        with ThreadPoolExecutor(max_workers=2) as pool:
            for future in as_completed([pool.submit(one, item) for item in files]):
                name = future.result()
                with db:
                    db.execute('UPDATE files SET completed=1 WHERE name=?', (name,))
                progress(name + ' verified')
        return revision
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='Offline dataset directory, for example dev/datasets/danbooru-2026')
    parser.add_argument('--source', default=SOURCE)
    parser.add_argument('--revision')
    args = parser.parse_args()
    download(args.destination, source=args.source, revision=args.revision,
             progress=lambda message: print(message, flush=True))


if __name__ == '__main__':
    main()
