"""Preview project cleanup, then delete only the entries in a reviewed JSON plan."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {
    'caches': ('dev/cache', 'dev/build', 'dev/tmp'),
    'backups': ('data/backups',),
    'verification': ('dev/verification',),
}
WEIGHTS = {'.onnx', '.onnx_data', '.ckpt', '.pt', '.pth', '.safetensors', '.gguf', '.parquet'}
PRESERVED = {'.git', '.worktrees', 'models', 'datasets', 'node_modules', '.venv', 'venv'}


def linked(path):
    metadata = path.lstat()
    return path.is_symlink() or bool(getattr(metadata, 'st_file_attributes', 0)
                                    & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))


def candidate(root, relative, group):
    """Accept only direct children of the fixed cleanup directories."""
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Path must be relative to the project: ' + str(relative))
    if relative.parent.as_posix() not in SOURCES.get(group, ()):
        raise ValueError('Outside cleanup scope: ' + str(relative))
    path = root
    for part in relative.parts:
        path = path / part
        if linked(path):
            raise ValueError('Link or junction preserved: ' + str(relative))
    if not path.resolve().is_relative_to(root):
        raise ValueError('Path escapes the project: ' + str(relative))
    return path


def tracked_paths(root):
    result = subprocess.run(['git', '-C', str(root), '-c', 'safe.directory=' + str(root),
                             'ls-files', '-z'], check=True, capture_output=True)
    return {os.fsdecode(name).replace('\\', '/') for name in result.stdout.split(b'\0') if name}


def snapshot(path, group):
    """Inspect metadata without following links or reading large file contents."""
    if group == 'backups' and (not path.is_dir()
            or {child.name for child in path.iterdir()} != {'dist'}
            or not (path / 'dist/index.html').is_file()):
        raise ValueError('Only standalone frontend dist backups are cleanable')
    digest = hashlib.sha256()
    size = 0
    newest = 0

    def visit(current):
        nonlocal size, newest
        if linked(current):
            raise ValueError('Contains a link or junction')
        name = current.name.lower()
        suffixes = {suffix.lower() for suffix in current.suffixes}
        if name in PRESERVED or suffixes & WEIGHTS or (
                '.bin' in suffixes and name.startswith(('model', 'pytorch_model'))):
            raise ValueError('Contains models, raw data, an environment or a repository')
        if group == 'backups' and (name in {'db', 'images', 'libraries', 'workflows'}
                or current.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.zip', '.7z', '.tar', '.gz'}
                or any(marker in name for marker in ('.sqlite', '.db-'))):
            raise ValueError('Contains a personal data backup')
        metadata = current.stat()
        if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            raise ValueError('Contains a special file')
        newest = max(newest, metadata.st_mtime_ns)
        digest.update(json.dumps([current.relative_to(path).as_posix(), metadata.st_mode,
                                  metadata.st_size, metadata.st_mtime_ns]).encode('utf-8'))
        if current.is_dir():
            for child in sorted(current.iterdir()):
                visit(child)
        else:
            size += metadata.st_size

    visit(path)
    return {'bytes': size, 'newest_ns': newest, 'fingerprint': digest.hexdigest()}


def inspect(root, relative, group, tracked):
    path = candidate(root, relative, group)
    prefix = os.path.normcase(Path(relative).as_posix()).replace('\\', '/')
    if any(os.path.normcase(name).replace('\\', '/') == prefix
           or os.path.normcase(name).replace('\\', '/').startswith(prefix + '/') for name in tracked):
        raise ValueError('Contains Git-tracked files')
    return path, snapshot(path, group)


def make_plan(root, groups, days):
    root = root.resolve()
    tracked = tracked_paths(root)
    cutoff = time.time_ns() - int(days * 86400 * 1_000_000_000)
    plan = {'version': 1, 'root': str(root), 'older_than_days': days,
            'entries': [], 'skipped': []}
    for group in groups:
        for source in SOURCES[group]:
            base = root / source
            if not base.exists():
                continue
            # Check the ancestors before enumerating a potentially linked directory.
            try:
                current = root
                for part in Path(source).parts:
                    current /= part
                    if linked(current):
                        raise ValueError('Link or junction preserved')
            except (OSError, ValueError) as error:
                plan['skipped'].append({'path': source, 'reason': str(error)})
                continue
            for path in sorted(base.iterdir()):
                relative = path.relative_to(root).as_posix()
                try:
                    _, state = inspect(root, relative, group, tracked)
                    if state['newest_ns'] > cutoff:
                        raise ValueError('Recently modified')
                    plan['entries'].append({'path': relative, 'group': group, **state})
                except (OSError, ValueError) as error:
                    plan['skipped'].append({'path': relative, 'reason': str(error)})
    return plan


def apply_plan(root, plan):
    root = root.resolve()
    if plan.get('version') != 1 or Path(plan['root']).resolve() != root:
        raise ValueError('Plan belongs to another project or format')
    tracked = tracked_paths(root)
    checked = []
    seen = set()
    # Validate the entire reviewed list before the first deletion.
    for entry in plan['entries']:
        relative, group = entry['path'], entry['group']
        if relative in seen:
            raise ValueError('Duplicate cleanup entry: ' + relative)
        seen.add(relative)
        path, state = inspect(root, relative, group, tracked)
        if state != {key: entry[key] for key in state}:
            raise ValueError('Changed since preview; create a new plan: ' + relative)
        checked.append((path, group, state))
    for path, group, state in checked:
        # A running build/test may have modified a later entry during cleanup.
        candidate(root, path.relative_to(root), group)
        if snapshot(path, group) != state:
            raise ValueError('Changed during cleanup; preserved: ' + str(path))
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        print('Deleted: ' + path.relative_to(root).as_posix())
    return len(checked)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--groups', nargs='+', choices=SOURCES,
                        help='Preview these groups (default: all three)')
    parser.add_argument('--older-than-days', type=float,
                        help='Keep recently modified entries (default: 7; use 0 to list all ages)')
    parser.add_argument('--plan', type=Path, help='Write the preview to this new JSON file')
    parser.add_argument('--apply', type=Path, help='Delete only entries in this reviewed JSON plan')
    args = parser.parse_args(argv)
    days = 7 if args.older_than_days is None else args.older_than_days
    if days < 0 or not days < float('inf'):
        parser.error('--older-than-days must be a finite nonnegative number')
    try:
        if args.apply:
            if args.plan or args.groups is not None or args.older_than_days is not None:
                parser.error('--apply uses the reviewed plan; omit preview options')
            plan = json.loads(args.apply.read_text(encoding='utf-8'))
            count = apply_plan(ROOT, plan)
            print(f'Cleanup complete: {count} entries.')
            return
        plan = make_plan(ROOT, list(dict.fromkeys(args.groups or SOURCES)), days)
        destination = args.plan or ROOT / 'dev/maintenance' / (
            'cleanup-plan-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8') as output:
            json.dump(plan, output, ensure_ascii=False, indent=2)
            output.write('\n')
        total = sum(entry['bytes'] for entry in plan['entries'])
        for entry in plan['entries']:
            modified = datetime.fromtimestamp(entry['newest_ns'] / 1e9, timezone.utc).isoformat()
            print(f"{entry['group']:12} {entry['bytes'] / 1024**2:10.2f} MiB  {modified}  {entry['path']}")
        print(f"Preview only: {len(plan['entries'])} entries, {total / 1024**3:.2f} GiB; "
              f"{len(plan['skipped'])} entries preserved.")
        print('Review the entries and skipped reasons in: ' + str(destination.resolve()))
        print('To delete the reviewed entries: python scripts/clean_project.py --apply "' + str(destination) + '"')
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Cleanup stopped: {error}\n')


if __name__ == '__main__':
    main()
