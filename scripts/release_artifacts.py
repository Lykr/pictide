"""Bind native archives and tested container digests to one release commit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {'windows-x64': 'win32-amd64', 'linux-x64': 'linux-x86_64',
             'macos-arm64': 'darwin-arm64', 'macos-x64': 'darwin-x86_64'}
ARCHITECTURES = {'amd64', 'arm64'}
REPOSITORY = 'ghcr.io/lykr/pictide'
DIAGNOSTICS = 'release-diagnostics.zip'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, document):
    Path(path).write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(root=ROOT):
    namespace = {}
    exec((Path(root) / 'backend/__init__.py').read_text(encoding='utf-8'), namespace)
    version = namespace['__version__']
    if version != read(Path(root) / 'web/package.json')['version']:
        raise ValueError('Backend/frontend versions differ')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    validate_identity(commit, 'v' + version)
    return dict(version=version, commit=commit)


def validate_identity(commit, tag):
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', tag):
        raise ValueError('Invalid release identity')


def native_record(directory, platform, commit, version):
    name = f'pictide-{version}-{PLATFORMS[platform]}.zip'
    return dict(schema=1, kind='portable', platform=platform, commit=commit, version=version,
                archive=name, sha256=digest(Path(directory) / name))


def check_native(directory, record):
    platform, version = record['platform'], record['version']
    name = f'pictide-{version}-{PLATFORMS[platform]}.zip'
    smoke = read(directory / f'smoke-report-{platform}.json')
    build = read(directory / f'build-report-{platform}.json')
    if (record['archive'] != name or digest(directory / name) != record['sha256']
            or not smoke['passed'] or not build['passed'] or smoke['version'] != version
            or smoke['archive'] != name or smoke['archive_sha256'] != record['sha256']
            or build['archive'].replace('\\', '/').rsplit('/', 1)[-1] != name):
        raise ValueError('Native reports do not match the tested archive')


def check_docker(directory, record):
    architecture = record['architecture']
    smoke = read(directory / f'docker-smoke-report-{architecture}.json')
    if (not re.fullmatch(r'sha256:[0-9a-f]{64}', record['digest'])
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', record['image_id'])
            or record['image'] != REPOSITORY + '@' + record['digest']
            or not smoke['passed'] or smoke['version'] != record['version']
            or smoke['architecture'] != architecture or smoke['image_id'] != record['image_id']
            or smoke['revision'] != record['commit']):
        raise ValueError('Docker reports do not match the tested image')


def write_native(directory, platform, commit, version):
    directory = Path(directory)
    record = native_record(directory, platform, commit, version)
    check_native(directory, record)
    write(directory / f'source-{platform}.json', record)
    return record


def write_docker(directory, architecture, commit, version, image_digest, image_id):
    directory = Path(directory)
    record = dict(schema=1, kind='docker', architecture=architecture, commit=commit, version=version,
                  image=REPOSITORY + '@' + image_digest, digest=image_digest, image_id=image_id)
    check_docker(directory, record)
    write(directory / f'source-docker-{architecture}.json', record)
    return record


def verify(directory, commit, tag):
    """Refuse missing platforms, mixed sources, or files changed after their smoke."""
    directory = Path(directory)
    validate_identity(commit, tag)
    native, docker = {}, {}
    for path in sorted(directory.glob('source-*.json')):
        record = read(path)
        if record.get('schema') != 1 or record.get('commit') != commit or record.get('version') != tag[1:]:
            raise ValueError('Release artifacts do not share the selected tag and commit')
        if record['kind'] == 'portable':
            platform = record['platform']
            if platform in native or platform not in PLATFORMS:
                raise ValueError('Unexpected native platform')
            check_native(directory, record)
            native[platform] = record
        elif record['kind'] == 'docker':
            architecture = record['architecture']
            if architecture in docker or architecture not in ARCHITECTURES:
                raise ValueError('Unexpected Docker architecture')
            check_docker(directory, record)
            docker[architecture] = record
        else:
            raise ValueError('Unexpected artifact kind')
    if set(native) != set(PLATFORMS) or set(docker) != ARCHITECTURES:
        raise ValueError('Expected four native packages and both Docker architectures')
    return dict(schema=1, tag=tag, version=tag[1:], commit=commit, portable=native, docker=docker)


def diagnostic_paths(directory):
    names = ['release.json']
    for platform in sorted(PLATFORMS):
        names.extend(f'{prefix}-{platform}.json' for prefix in ('build-report', 'smoke-report', 'source'))
    for architecture in sorted(ARCHITECTURES):
        names.extend(f'{prefix}-{architecture}.json' for prefix in ('docker-smoke-report', 'source-docker'))
    return [Path(directory) / name for name in names]


def bundle_diagnostics(directory):
    paths = diagnostic_paths(directory)
    if not all(path.is_file() for path in paths):
        raise ValueError('Expected complete release diagnostics')
    target = Path(directory) / DIAGNOSTICS
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, arcname=path.name)
    return target


def release_downloads(directory):
    """Keep the public download list explicit; preserve all engineering JSON in one ZIP."""
    directory = Path(directory)
    release = read(directory / 'release.json')
    validate_identity(release['commit'], release['tag'])
    version = release['version']
    if release['tag'] != 'v' + version:
        raise ValueError('Release tag and version differ')
    files = []
    for kind, targets in [('portable', PLATFORMS), ('docker', ARCHITECTURES)]:
        if set(release[kind]) != set(targets):
            raise ValueError('Expected all six release artifacts')
        for key, record in sorted(release[kind].items()):
            name = (f'pictide-{version}-{PLATFORMS[key]}.zip' if kind == 'portable'
                    else f'pictide-{version}-linux-{key}-docker.tar.gz')
            path = directory / name
            if record['archive'] != name or digest(path) != record['sha256']:
                raise ValueError('Download differs from the verified release artifact')
            files.append(path)
    files.extend([directory / 'compose.yaml', directory / 'update.json', bundle_diagnostics(directory)])
    checksums = directory / 'SHA256SUMS'
    checksums.write_text(''.join(digest(path) + '  ' + path.name + '\n' for path in sorted(files)), encoding='utf-8')
    return sorted(files + [checksums])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['identity', 'native', 'verify'])
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--platform', choices=PLATFORMS)
    parser.add_argument('--commit')
    parser.add_argument('--version')
    parser.add_argument('--tag')
    args = parser.parse_args()
    if args.operation == 'identity':
        result = identity()
        if args.tag != 'v' + result['version']:
            raise ValueError('Release tag and source version differ')
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f"commit={result['commit']}\ntag={args.tag}\nversion={result['version']}\n")
    elif args.operation == 'native':
        current = identity()
        if current['commit'] != args.commit or current['version'] != args.version:
            raise ValueError('Native checkout differs from the release source')
        result = write_native(args.directory, args.platform, args.commit, args.version)
    else:
        result = verify(args.directory, args.commit, args.tag)
        write(args.directory / 'release.json', result)
    print(json.dumps(result))
