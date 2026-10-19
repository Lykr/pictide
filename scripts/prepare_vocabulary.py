"""Prepare a versioned vocabulary for local packaging and GitHub Actions."""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from corpus import download
from corpus.portable import DEFAULT_PREBUILT_LOCK, prepare_vocabulary, write_report


def export_vocabulary(dataset_dir, cache_dir, profile, *, output_dir=None,
                      resource_lock=DEFAULT_PREBUILT_LOCK, lock_path=None):
    arguments = {'lock_path': lock_path} if lock_path is not None else {}
    library, report = prepare_vocabulary(dataset_dir, cache_dir, profile, **arguments,
                                         progress=lambda message: print(message, flush=True))
    key = report['fingerprint']
    output = Path(output_dir or Path(cache_dir) / 'exports' / key).resolve()
    if output == library.parent:
        raise ValueError('Choose an export directory separate from the processing cache')
    expected_report = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    if output.exists():
        if (not download.verified(output / 'vocabulary.sqlite3', report['file'])
                or not (output / 'report.json').is_file()
                or (output / 'report.json').read_bytes() != expected_report):
            raise ValueError('Export already exists with different/incomplete contents; choose a new --output-dir')
    else:
        output.mkdir(parents=True)
        shutil.copyfile(library, output / 'vocabulary.sqlite3')
        (output / 'report.json').write_bytes(expected_report)
    files = [dict(path=name, bytes=(output / name).stat().st_size,
                  sha256=download.sha256(output / name)) for name in ('vocabulary.sqlite3', 'report.json')]
    locked = dict(release_tag='corpus-' + key, fingerprint=key, files=files)
    write_report(Path(resource_lock), locked)
    print(f'Export ready: {output}', flush=True)
    print(f'Resource lock updated: {resource_lock}', flush=True)
    print('Upload this resource before pushing an application version tag:', flush=True)
    command = ['gh', 'release', 'create', locked['release_tag'],
               str(output / 'vocabulary.sqlite3'), str(output / 'report.json'),
               '--title', 'Pictide vocabulary ' + key[:12],
               '--notes', 'Pinned statistical vocabulary and processing provenance for portable builds.',
               '--prerelease', '--latest=false']
    # JSON argv remains unambiguous on every platform, alongside a convenient shell example.
    print('Upload arguments: ' + json.dumps(command), flush=True)
    print(shlex.join(command), flush=True)
    return locked


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-dir', type=Path, default=ROOT / 'dev/datasets/danbooru-2026')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'dev/cache/portable')
    parser.add_argument('--profile', type=Path, default=ROOT / 'corpus/profiles/compact.json')
    parser.add_argument('--output-dir', type=Path, help='New resource export directory (default: cache/exports/<fingerprint>)')
    args = parser.parse_args()
    export_vocabulary(args.dataset_dir, args.cache_dir, args.profile, output_dir=args.output_dir)
