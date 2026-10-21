"""Write the update manifest only from successful native package/update smoke reports."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import __version__
from backend.updates.releases import version


def write_manifest(directory, policy_path=ROOT / 'scripts/update-policy.json'):
    directory = Path(directory)
    policy = json.loads(Path(policy_path).read_text(encoding='utf8'))
    allowed = policy['direct_upgrade_from']
    if (policy['schema'] != 1 or type(policy.get('requires_data_migration')) is not bool
            or version(allowed['minimum']) >= version(allowed['maximum_exclusive'])):
        raise ValueError('Invalid direct-upgrade compatibility range')
    assets = {}
    for archive in sorted(directory.glob('pictide-*.zip')):
        reports = [json.loads(path.read_text(encoding='utf8')) for path in directory.glob('smoke-report-*.json')]
        report = next(item for item in reports if item['archive'] == archive.name)
        builds = [json.loads(path.read_text(encoding='utf8')) for path in directory.glob('build-report-*.json')]
        build = next(item for item in builds if item['archive'].replace('\\', '/').rsplit('/', 1)[-1] == archive.name)
        with archive.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if not report['passed'] or report['version'] != __version__ or not build['passed'] or report['archive_sha256'] != digest:
            raise ValueError('Release reports do not match the verified archive')
        name = archive.name.removeprefix('pictide-' + __version__ + '-').removesuffix('.zip')
        if name == archive.name or name not in ('win32-amd64', 'darwin-arm64', 'darwin-x86_64', 'linux-x86_64'):
            raise ValueError('Unexpected native release asset')
        assets[name] = dict(name=archive.name, bytes=archive.stat().st_size, sha256=digest,
                            unpacked_bytes=int(build['unpacked_bytes'] * 1.05) + 1024 * 1024,
                            install_verified=bool(report.get('updates_verified')))
    if not assets:
        raise ValueError('No verified release assets')
    document = dict(schema=1, version=__version__, requires_data_migration=policy['requires_data_migration'],
                    direct_upgrade_from=allowed, assets=assets)
    (directory / 'update.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf8')
    return document


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    write_manifest(parser.parse_args().directory)
