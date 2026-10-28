"""Verify a built Docker image with fresh Compose data and offline container replacement."""
import argparse
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
from threading import Thread
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
import uuid

ROOT = Path(__file__).resolve().parents[1]
OPENER = build_opener(ProxyHandler({}))


def command(*args, payload=None, check=True, env=None):
    result = subprocess.run(args, input=payload, text=True, encoding='utf-8', capture_output=True,
                            cwd=ROOT, env=env, timeout=120)
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args) + '\n' + result.stdout[-4000:] + result.stderr[-8000:])
    return result


def docker_json(*args):
    return json.loads(command('docker', *args).stdout)


def inside(container, source):
    return json.loads(command('docker', 'exec', '-i', container, 'python', '-', payload=source).stdout)


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attributes):
        for key, value in attributes:
            if key in {'src', 'href'} and value and value.startswith('/static/ui/'):
                self.paths.add(value)


class ImageAPIProbe(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"service":"mock-image-api"}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def smoke(image, report_path, timeout=900):
    report_path = Path(report_path)
    project = 'pictide-smoke-' + uuid.uuid4().hex[:12]
    offline = project + '-offline'
    environment = dict(os.environ, PICTIDE_IMAGE=image, PICTIDE_PORT='0', PICTIDE_BIND='127.0.0.1',
                       PICTIDE_VOCABULARY='filtered')
    compose = ['docker', 'compose', '--project-name', project, '--file', str(ROOT / 'compose.yaml')]
    report = {'passed': False, 'image': image, 'checks': []}
    started, compose_started, offline_started = time.monotonic(), False, False
    container = None
    failure = None
    try:
        command(*compose, 'config', '--quiet', env=environment)
        info = docker_json('image', 'inspect', image)[0]
        report.update(image_id=info['Id'], image_bytes=info['Size'], architecture=info['Architecture'])
        labels = info['Config'].get('Labels') or {}
        report['revision'] = labels.get('org.opencontainers.image.revision')
        assert info['Config']['User'] == '10001:10001'
        pristine = command('docker', 'run', '--rm', '--entrypoint', 'python', image, '-c',
            "import importlib.util,json,os,pathlib,shutil; "
            "root=pathlib.Path('/app'); "
            "assert os.getuid()==10001; assert not any(pathlib.Path('/data').iterdir()); "
            "assert not any(p.suffix in {'.sqlite3','.onnx','.safetensors'} for p in root.rglob('*')); "
            "assert shutil.which('node') is None; assert importlib.util.find_spec('PyInstaller') is None; "
            "assert (root/'web/dist/index.html').is_file(); "
            "assert (root/'backend/setup/vocabularies.json').is_file(); "
            "assert (root/'backend/recommendation/model.json').is_file(); "
            "print(json.dumps({'uid':os.getuid(),'python':os.sys.version}))").stdout
        report['runtime'] = json.loads(pristine)
        report['checks'].append('non-root Python runtime, built frontend and catalogs; no application databases, weights or Node build tools')
        compose_started = True
        command(*compose, 'up', '--detach', '--no-build', env=environment)
        container = command(*compose, 'ps', '--quiet', 'pictide', env=environment).stdout.strip()
        record = docker_json('inspect', container)[0]
        binding = record['NetworkSettings']['Ports']['8189/tcp'][0]
        assert binding['HostIp'] == '127.0.0.1'
        base = 'http://127.0.0.1:' + binding['HostPort']

        def get(path, *, document=True, method='GET', payload=None):
            data = json.dumps(payload).encode() if payload is not None else None
            request = Request(base + path, data=data, method=method,
                              headers={'Content-Type': 'application/json'} if data is not None else {})
            with OPENER.open(request, timeout=10) as response:
                content = response.read()
                assert response.status == 200
                return json.loads(content) if document else content

        def wait_ready(name, fetch, budget):
            deadline = time.monotonic() + budget
            while True:
                state = docker_json('inspect', name)[0]['State']
                if not state['Running']:
                    raise RuntimeError('Container exited during preparation: ' + json.dumps(state))
                try:
                    bootstrap = fetch()
                    if state.get('Health', {}).get('Status') == 'healthy':
                        return bootstrap
                except (URLError, TimeoutError, ConnectionError, RuntimeError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError('Container did not become healthy before timeout')
                time.sleep(1)

        bootstrap = wait_ready(container, lambda: get('/api/bootstrap'), timeout)
        report['startup_seconds'] = round(time.monotonic() - started, 2)
        assert bootstrap['name'] == 'Pictide' and bootstrap['data_directory'] == '/data'
        assert not bootstrap['backends'] and not bootstrap['jobs'] and not bootstrap['artifacts']
        assert bootstrap['recommendation']['available']
        libraries = get('/api/candidate/library')
        assert libraries['selected'].startswith('pictide-vocabulary-filtered')
        report['version'] = bootstrap['version']
        if labels.get('org.opencontainers.image.version'):
            assert report['version'] == labels['org.opencontainers.image.version']
        report['checks'].append('Compose loopback port and healthy HTTP startup with a real first-start filtered/MiniLM download')
        assets = Assets()
        assets.feed(get('/', document=False).decode())
        assert assets.paths
        for path in assets.paths:
            assert get(path, document=False)
        report['checks'].append('compiled frontend and referenced assets served from the container')
        with HTTPServer(('0.0.0.0', 0), ImageAPIProbe) as probe:
            thread = Thread(target=probe.serve_forever, daemon=True)
            thread.start()
            try:
                result = inside(container, "import json; from urllib.request import ProxyHandler,build_opener; "
                    f"response=build_opener(ProxyHandler({{}})).open('http://host.docker.internal:{probe.server_port}',timeout=5); "
                    "print(json.dumps(json.loads(response.read())))")
                assert result == {'service': 'mock-image-api'}
            finally:
                probe.shutdown()
                thread.join(timeout=5)
        report['checks'].append('container reaches a neutral host-side API through host.docker.internal')
        inference_source = (ROOT / 'scripts/smoke_inference.py').read_text(encoding='utf-8') + '''
import json
from urllib.request import ProxyHandler, build_opener
opener = build_opener(ProxyHandler({}))
def get(path, *, timeout=5):
    with opener.open('http://127.0.0.1:8189' + path, timeout=timeout) as response:
        return json.loads(response.read())
print(json.dumps(smoke_inference('/data', get)))
'''
        report['inference'] = inside(container, inference_source)
        report['checks'].append('actual CPU MiniLM scoring through the running application with fresh embeddings')
        settings = get('/api/settings/general', method='PUT',
                       payload={'theme': 'dark', 'language': 'en', 'image_transitions': False})
        inside(container, '''
import base64,json,pathlib
marker=pathlib.Path('/data/images/docker-smoke.png')
assert not marker.exists()
marker.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='))
print(json.dumps({'created':True}))
''')
        data_probe = '''
import hashlib,json,pathlib,sqlite3
from contextlib import closing
root=pathlib.Path('/data')
catalog=json.loads(pathlib.Path('/app/backend/recommendation/model.json').read_text())
files={}
for item in catalog['files']:
    path=root/'models/minilm'/item['path']
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.stat().st_size==item['bytes'] and digest==item['sha256']
    files[item['path']]=digest
with closing(sqlite3.connect(root/'db/pictide.sqlite3')) as db:
    assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    counts={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('jobs','artifacts','recommendation_vectors')}
marker=root/'images/docker-smoke.png'
assert marker.is_file()
print(json.dumps({'models':files,'records':counts,'image_sha256':hashlib.sha256(marker.read_bytes()).hexdigest()}))
'''
        before = inside(container, data_probe)
        assert before['records'] == {'jobs': 1, 'artifacts': 1, 'recommendation_vectors': 2}
        volume = next(item['Name'] for item in docker_json('inspect', container)[0]['Mounts'] if item['Destination'] == '/data')
        command(*compose, 'stop', env=environment)
        assert docker_json('inspect', container)[0]['State']['ExitCode'] == 0
        command(*compose, 'rm', '--force', env=environment)
        offline_started = True
        command('docker', 'run', '--detach', '--init', '--name', offline, '--network', 'none',
                '--mount', f'type=volume,source={volume},target=/data', image)
        request_source = '''
import json
from urllib.request import ProxyHandler,build_opener
opener=build_opener(ProxyHandler({}))
with opener.open('http://127.0.0.1:8189/api/bootstrap',timeout=3) as response:
    print(json.dumps(json.loads(response.read())))
'''
        restored = wait_ready(offline, lambda: inside(offline, request_source), 90)
        assert restored['name'] == 'Pictide' and restored['version'] == report['version']
        after = inside(offline, data_probe)
        assert before == after
        restored_settings = inside(offline, request_source.replace('/api/bootstrap', '/api/settings/general'))
        assert restored_settings == settings
        restored_libraries = inside(offline, request_source.replace('/api/bootstrap', '/api/candidate/library'))
        assert restored_libraries['selected'] == libraries['selected']
        report['checks'].append('graceful SIGTERM and offline replacement retain SQLite records, settings, images and verified resources in the named volume')
        report['passed'] = True
    except Exception as error:
        failure = error
        report['error'] = str(error)
    finally:
        if not report['passed']:
            for name in (container, offline if offline_started else None):
                if name:
                    report.setdefault('container_logs', []).append(command('docker', 'logs', '--tail', '160', name, check=False).stdout[-16000:])
        if offline_started:
            command('docker', 'rm', '--force', offline, check=False)
        if compose_started:
            command(*compose, 'down', '--volumes', '--remove-orphans', check=False, env=environment)
        report['seconds'] = round(time.monotonic() - started, 2)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if failure is not None:
        raise RuntimeError(f'Docker smoke failed; see {report_path}: {failure}') from failure
    print(json.dumps(report), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='pictide:local')
    parser.add_argument('--report', type=Path, default=ROOT / 'dev/verification/docker/smoke-report.json')
    parser.add_argument('--timeout', type=float, default=900)
    args = parser.parse_args()
    smoke(args.image, args.report, args.timeout)
