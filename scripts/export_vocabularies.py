"""Export filtered and all-ratings vocabularies as one versioned release resource."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from corpus import download
from corpus.portable import fingerprint, prepare_vocabulary


def json_bytes(document):
    return (json.dumps(document, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def export_vocabularies(dataset_dir, cache_dir, *, output_dir=None, profiles=None, lock_path=None):
    """Reuse processing caches and export both editions without changing prebuilt.json."""
    profiles = profiles or {
        'filtered': ROOT / 'corpus/profiles/compact.json',
        'all-ratings': ROOT / 'corpus/profiles/all-ratings.json',
    }
    if set(profiles) != {'filtered', 'all-ratings'}:
        raise ValueError('Provide profiles for filtered and all-ratings')
    arguments = {'lock_path': lock_path} if lock_path is not None else {}
    copies, documents, editions, files = {}, {}, {}, []
    for edition in ('filtered', 'all-ratings'):
        profile = Path(profiles[edition]).resolve()
        library, production = prepare_vocabulary(
            dataset_dir, cache_dir, profile, **arguments,
            progress=lambda message: print(message, flush=True))
        name = f'pictide-vocabulary-{edition}.sqlite3'
        report_name = f'pictide-vocabulary-{edition}.report.json'
        library_file = {**production['file'], 'path': name}
        report = {**production, 'edition': edition, 'file': library_file}
        payload = json_bytes(report)
        report_file = dict(path=report_name, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        copies[name] = library
        documents[report_name] = payload
        files.extend((library_file, report_file))
        profile_name = profile.relative_to(ROOT).as_posix() if profile.is_relative_to(ROOT) else str(profile)
        editions[edition] = dict(profile=profile_name, fingerprint=production['fingerprint'],
                                 file=library_file, report=report_file)
        print(f'{edition}: ' + json.dumps(production['statistics'], ensure_ascii=False), flush=True)

    contents = dict(editions=editions, files=files)
    key = fingerprint(contents)
    manifest = dict(**contents, fingerprint=key, release_tag='corpus-editions-' + key)
    documents['manifest.json'] = json_bytes(manifest)
    manifest_file = dict(path='manifest.json', sha256=hashlib.sha256(documents['manifest.json']).hexdigest())
    documents['SHA256SUMS'] = ''.join(
        f'{item["sha256"]}  {item["path"]}\n' for item in [*files, manifest_file]
    ).encode('utf-8')
    output = Path(output_dir or ROOT / 'releases' / ('vocabularies-' + key[:12])).expanduser().resolve()
    expected_names = set(copies) | set(documents)
    if output.exists():
        if (not output.is_dir() or {item.name for item in output.iterdir()} != expected_names
                or any(not download.verified(output / item['path'], item) for item in files)
                or any((output / name).read_bytes() != payload for name, payload in documents.items())):
            raise ValueError('Export already exists with different/incomplete contents; choose a new --output-dir')
        print(f'Export verified: {output}', flush=True)
    else:
        output.mkdir(parents=True)
        for name, library in copies.items():
            shutil.copyfile(library, output / name)
        for name, payload in documents.items():
            (output / name).write_bytes(payload)
        print(f'Export ready: {output}', flush=True)

    command = ['gh', 'release', 'create', manifest['release_tag'],
               *(str(output / name) for name in [*(item['path'] for item in files), 'manifest.json', 'SHA256SUMS']),
               '--title', 'Pictide vocabularies: filtered and all ratings',
               '--notes', 'Statistical vocabularies, processing provenance, and SHA-256 checksums. '
               'Portable packages use filtered by default; all-ratings is an optional manual replacement.',
               '--prerelease', '--latest=false']
    print('Upload arguments: ' + json.dumps(command), flush=True)
    print(shlex.join(command), flush=True)
    return dict(output=str(output), manifest=manifest, upload_arguments=command)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir', type=Path, default=ROOT / 'dev/datasets/danbooru-2026')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'dev/cache/portable')
    parser.add_argument('--output-dir', type=Path,
                        help='New export directory (default: releases/vocabularies-<content fingerprint>)')
    args = parser.parse_args()
    export_vocabularies(args.dataset_dir, args.cache_dir, output_dir=args.output_dir)
