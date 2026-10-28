"""Stage tested images, then publish the same digests without rebuilding."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.release_artifacts import REPOSITORY, digest, identity, read, verify, write, write_docker


def run(*args, check=True, env=None):
    result = subprocess.run(args, text=True, capture_output=True, env=env, timeout=600)
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args) + '\n' + result.stderr[-8000:])
    return result


def image_info(image, record):
    info, = json.loads(run('docker', 'image', 'inspect', image).stdout)
    labels = info['Config']['Labels']
    if (info['Id'] != record['image_id'] or info['Architecture'] != record['architecture']
            or info['Os'] != 'linux' or labels['org.opencontainers.image.revision'] != record['commit']
            or labels['org.opencontainers.image.version'] != record['version']):
        raise ValueError('Registry image differs from the tested release source')


def pushed_digest(output):
    matches = set(re.findall(r'(?:^|@|\s)(sha256:[0-9a-f]{64})(?=\s|$)', output))
    if len(matches) != 1:
        raise ValueError('Expected one registry digest in Docker push output: ' + output)
    return matches.pop()


def stage(directory, image, build_id):
    current = identity()
    if not re.fullmatch(r'[0-9]+-[0-9]+', build_id):
        raise ValueError('Expected a run ID and attempt')
    report = read(Path(directory) / 'smoke-report.json')
    record = dict(current, architecture=report['architecture'], image_id=report['image_id'])
    image_info(image, record)
    if not report['passed'] or report['version'] != current['version'] or report['revision'] != current['commit']:
        raise ValueError('Only a successful smoke of this checkout can be staged')
    target = f"{REPOSITORY}:build-{current['commit']}-{build_id}-{record['architecture']}"
    run('docker', 'tag', image, target)
    pushed = run('docker', 'push', target)
    image_digest = pushed_digest(pushed.stdout + '\n' + pushed.stderr)
    shutil.copyfile(Path(directory) / 'smoke-report.json',
                    Path(directory) / f"docker-smoke-report-{record['architecture']}.json")
    return write_docker(directory, record['architecture'], current['commit'], current['version'],
                        image_digest, record['image_id'])


def ensure_new_version(image):
    result = run('docker', 'manifest', 'inspect', image, check=False)
    if not result.returncode:
        raise ValueError('Refusing to replace an existing versioned image: ' + image)
    if not any(message in result.stderr.lower() for message in ('manifest unknown', 'no such manifest', 'not found')):
        raise RuntimeError('Could not check the versioned image: ' + result.stderr)


def manifest(image, records):
    run('docker', 'manifest', 'create', image, *(record['image'] for record in records.values()))
    for architecture, record in records.items():
        run('docker', 'manifest', 'annotate', image, record['image'], '--os', 'linux', '--arch', architecture)
    return pushed_digest(run('docker', 'manifest', 'push', image).stdout)


def export_image(image, archive):
    with gzip.open(archive, 'wb', compresslevel=6) as output:
        with subprocess.Popen(['docker', 'save', image], stdout=subprocess.PIPE) as process:
            shutil.copyfileobj(process.stdout, output)
            if process.wait(timeout=600):
                raise RuntimeError('Could not export the tested image')


def publish(directory, commit, tag):
    directory = Path(directory)
    release = verify(directory, commit, tag)
    release['tooling_commit'] = os.environ.get('RELEASE_TOOLING_COMMIT', commit)
    versioned = REPOSITORY + ':' + release['version']
    # A first GHCR publication needs public package visibility before any stable tag.
    with tempfile.TemporaryDirectory() as config:
        for record in release['docker'].values():
            run('docker', 'manifest', 'inspect', record['image'], env=dict(os.environ, DOCKER_CONFIG=config))
    ensure_new_version(versioned)
    for architecture, record in release['docker'].items():
        run('docker', 'pull', '--platform', 'linux/' + architecture, record['image'])
        image_info(record['image'], record)
        run('docker', 'tag', record['image'], versioned)
        archive = directory / f"pictide-{release['version']}-linux-{architecture}-docker.tar.gz"
        export_image(versioned, archive)
        record.update(archive=archive.name, sha256=digest(archive))
    release['image'] = versioned
    release['image_digest'] = manifest(versioned, release['docker'])
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', release['image_digest']):
        raise ValueError('Registry did not return an index digest')
    # Check public pull access independently of the publishing account.
    with tempfile.TemporaryDirectory() as config:
        environment = dict(os.environ, DOCKER_CONFIG=config)
        public = json.loads(run('docker', 'manifest', 'inspect', versioned, env=environment).stdout)
        actual = {item['platform']['architecture']: item['digest'] for item in public['manifests']}
        if actual != {key: value['digest'] for key, value in release['docker'].items()}:
            raise ValueError('Public image manifest differs from the verified images')
        for architecture in release['docker']:
            run('docker', 'pull', '--platform', 'linux/' + architecture, versioned, env=environment)
    # A downloaded Compose file follows this release; repository users follow latest.
    source = Path(__file__).resolve().parents[1] / 'compose.yaml'
    compose = source.read_text(encoding='utf-8').replace(REPOSITORY + ':latest', versioned)
    (directory / 'compose.yaml').write_text(compose, encoding='utf-8')
    write(directory / 'release.json', release)
    return release


def latest(directory):
    release = read(Path(directory) / 'release.json')
    if '-' not in release['version']:
        return manifest(REPOSITORY + ':latest', release['docker'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['stage', 'publish', 'latest'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--image')
    parser.add_argument('--build-id')
    parser.add_argument('--commit')
    parser.add_argument('--tag')
    args = parser.parse_args()
    if args.operation == 'stage':
        result = stage(args.directory, args.image, args.build_id)
    elif args.operation == 'publish':
        result = publish(args.directory, args.commit, args.tag)
    else:
        result = latest(args.directory)
    print(json.dumps(result))
