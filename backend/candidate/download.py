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


def download(destination, *, source=SOURCE, revision=None, progress=print):
    destination = Path(destination)
    raw = destination / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    if revision is None:
        with response('https://huggingface.co/api/datasets/' + source) as stream:
            revision = json.load(stream)['sha']
    with response(f'https://huggingface.co/api/datasets/{source}/tree/{revision}?recursive=true&expand=false') as stream:
        files = [item for item in json.load(stream) if item['path'].endswith('.parquet')]
    db = sqlite3.connect(destination / 'download.sqlite3')
    db.execute('CREATE TABLE IF NOT EXISTS files (name TEXT PRIMARY KEY, revision TEXT, size INTEGER, sha256 TEXT, completed INTEGER NOT NULL DEFAULT 0)')
    try:
        for item in files:
            db.execute('INSERT INTO files(name,revision,size,sha256) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET revision=excluded.revision,size=excluded.size,sha256=excluded.sha256',
                       (item['path'], revision, item['size'], item['lfs']['oid']))
        db.commit()
        progress(f'{source}@{revision}: {len(files)} shards, {sum(item["size"] for item in files):,} bytes')

        def one(item):
            path = raw / item['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(path.suffix + '.part')
            if path.exists():
                if path.stat().st_size != item['size'] or sha256(path) != item['lfs']['oid']:
                    raise ValueError(f'Existing file failed verification: {path}')
                return item['path']
            url = f'https://huggingface.co/datasets/{source}/resolve/{revision}/{item["path"]}?download=true'
            for attempt in range(4):
                try:
                    offset = partial.stat().st_size if partial.exists() else 0
                    with response(url, {'Range': f'bytes={offset}-'} if offset else {}) as stream:
                        append = bool(offset and stream.status == 206)
                        if append and not stream.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                            raise ValueError('Unexpected download range')
                        with partial.open('ab' if append else 'wb') as output:
                            while chunk := stream.read(2 * 1024 * 1024):
                                output.write(chunk)
                    if partial.stat().st_size != item['size'] or sha256(partial) != item['lfs']['oid']:
                        raise ValueError(f'Download failed verification: {item["path"]}')
                    os.replace(partial, path)
                    return item['path']
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2)
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
    parser.add_argument('destination', type=Path, help='Dataset directory under the application data directory')
    parser.add_argument('--source', default=SOURCE)
    parser.add_argument('--revision')
    args = parser.parse_args()
    download(args.destination, source=args.source, revision=args.revision,
             progress=lambda message: print(message, flush=True))


if __name__ == '__main__':
    main()
