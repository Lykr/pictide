import gzip
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import release_artifacts as artifacts, release_docker as docker

COMMIT = 'a' * 40
VERSION = '0.10.0'


class UnifiedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for platform, suffix in artifacts.PLATFORMS.items():
            archive = self.root / f'pictide-{VERSION}-{suffix}.zip'
            archive.write_bytes(('verified-' + platform).encode())
            artifacts.write(self.root / f'smoke-report-{platform}.json', dict(
                passed=True, version=VERSION, archive=archive.name, archive_sha256=artifacts.digest(archive)))
            artifacts.write(self.root / f'build-report-{platform}.json', dict(
                passed=True, archive='D:\\build\\' + archive.name))
            artifacts.write_native(self.root, platform, COMMIT, VERSION)
        for architecture, marker in [('amd64', 'b'), ('arm64', 'c')]:
            image_id = 'sha256:' + marker * 64
            artifacts.write(self.root / f'docker-smoke-report-{architecture}.json', dict(
                passed=True, version=VERSION, revision=COMMIT, architecture=architecture, image_id=image_id))
            artifacts.write_docker(self.root, architecture, COMMIT, VERSION, 'sha256:' + marker * 64, image_id)

    def verify(self):
        return artifacts.verify(self.root, COMMIT, 'v' + VERSION)

    def change(self, filename, **fields):
        path = self.root / filename
        document = artifacts.read(path)
        document.update(fields)
        artifacts.write(path, document)

    def test_all_six_outputs_share_an_immutable_identity(self):
        release = self.verify()
        self.assertEqual(release['commit'], COMMIT)
        self.assertEqual(len(release['portable']), 4)
        self.assertEqual(set(release['docker']), {'amd64', 'arm64'})

    def test_rejects_mixed_commits_and_versions(self):
        for fields in [dict(commit='d' * 40), dict(version='0.9.0')]:
            with self.subTest(fields=fields):
                self.change('source-docker-arm64.json', **fields)
                with self.assertRaisesRegex(ValueError, 'share the selected tag and commit'):
                    self.verify()
                self.change('source-docker-arm64.json', commit=COMMIT, version=VERSION)

    def test_rejects_missing_architecture_or_platform(self):
        for name in ['source-docker-arm64.json', 'source-macos-x64.json']:
            path = self.root / name
            original = path.read_bytes()
            path.unlink()
            with self.assertRaisesRegex(ValueError, 'four native packages and both Docker'):
                self.verify()
            path.write_bytes(original)

    def test_rejects_changed_archive_and_mismatched_build_report(self):
        record = self.verify()['portable']['windows-x64']
        archive = self.root / record['archive']
        original = archive.read_bytes()
        archive.write_bytes(b'replaced after its smoke')
        with self.assertRaisesRegex(ValueError, 'tested archive'):
            self.verify()
        archive.write_bytes(original)
        self.change('build-report-windows-x64.json', archive='another.zip')
        with self.assertRaisesRegex(ValueError, 'tested archive'):
            self.verify()

    def test_rejects_failed_smoke_changed_image_or_other_registry(self):
        for fields in [dict(passed=False), dict(image_id='sha256:' + 'd' * 64), dict(revision='d' * 40)]:
            original = (self.root / 'docker-smoke-report-amd64.json').read_bytes()
            self.change('docker-smoke-report-amd64.json', **fields)
            with self.assertRaisesRegex(ValueError, 'tested image'):
                self.verify()
            (self.root / 'docker-smoke-report-amd64.json').write_bytes(original)
        self.change('source-docker-amd64.json', image='other.example/image@sha256:' + 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'tested image'):
            self.verify()

    def test_publisher_does_nothing_when_sources_disagree(self):
        self.change('source-linux-x64.json', commit='d' * 40)
        with patch.object(docker, 'run') as command:
            with self.assertRaises(ValueError):
                docker.publish(self.root, COMMIT, 'v' + VERSION)
        command.assert_not_called()

    def test_publisher_exports_and_publishes_only_verified_digests(self):
        release = self.verify()
        manifest = dict(manifests=[dict(platform=dict(architecture=key), digest=value['digest'])
                                  for key, value in release['docker'].items()])

        def command(*args, **kwargs):
            if args[:4] == ('docker', 'manifest', 'inspect', artifacts.REPOSITORY + ':' + VERSION):
                if kwargs.get('check') is False:
                    return subprocess.CompletedProcess(args, 1, '', 'manifest unknown')
                return subprocess.CompletedProcess(args, 0, json.dumps(manifest), '')
            return subprocess.CompletedProcess(args, 0, '', '')

        with patch.object(docker, 'run', side_effect=command) as commands, \
                patch.object(docker, 'image_info') as inspect, \
                patch.object(docker, 'export_image', side_effect=lambda image, path: path.write_bytes(b'archive')), \
                patch.object(docker, 'manifest', return_value='sha256:' + 'e' * 64) as publish:
            result = docker.publish(self.root, COMMIT, 'v' + VERSION)
        self.assertEqual(inspect.call_count, 2)
        self.assertEqual(publish.call_args.args[0], artifacts.REPOSITORY + ':' + VERSION)
        pulls = [call.args for call in commands.call_args_list if call.args[:2] == ('docker', 'pull')]
        self.assertEqual(len(pulls), 4)  # two authenticated digest pulls, two anonymous version pulls
        self.assertTrue(all('@sha256:' in call[-1] for call in pulls[:2]))
        self.assertNotIn('build', [part for call in commands.call_args_list for part in call.args])
        self.assertEqual(result['commit'], COMMIT)
        self.assertIn(artifacts.REPOSITORY + ':' + VERSION, (self.root / 'compose.yaml').read_text())
        self.assertTrue(all((self.root / item['archive']).is_file() for item in result['docker'].values()))

    def test_existing_version_and_registry_errors_do_not_overwrite(self):
        for result, error in [(subprocess.CompletedProcess([], 0, '{}', ''), ValueError),
                              (subprocess.CompletedProcess([], 1, '', 'denied'), RuntimeError)]:
            with patch.object(docker, 'run', return_value=result):
                with self.assertRaises(error):
                    docker.ensure_new_version(artifacts.REPOSITORY + ':' + VERSION)

    def test_registry_image_must_match_tested_config_and_source_labels(self):
        record = self.verify()['docker']['amd64']
        info = dict(Id=record['image_id'], Architecture='amd64', Os='linux', Config=dict(Labels={
            'org.opencontainers.image.revision': COMMIT, 'org.opencontainers.image.version': VERSION}))
        with patch.object(docker, 'run', return_value=Mock(stdout=json.dumps([info]))):
            docker.image_info(record['image'], record)
            with self.assertRaisesRegex(ValueError, 'tested release source'):
                docker.image_info(record['image'], dict(record, commit='d' * 40))

    def test_image_download_is_a_real_gzip_stream(self):
        process = Mock(stdout=io.BytesIO(b'a fake Docker tar stream'))
        process.wait.return_value = 0
        process.__enter__ = Mock(return_value=process)
        process.__exit__ = Mock(return_value=False)
        archive = self.root / 'image.tar.gz'
        with patch.object(docker.subprocess, 'Popen', return_value=process):
            docker.export_image('verified:image', archive)
        self.assertEqual(gzip.decompress(archive.read_bytes()), b'a fake Docker tar stream')

    def test_prereleases_do_not_advance_latest(self):
        artifacts.write(self.root / 'release.json', dict(version='0.10.0-rc.1', docker={}))
        with patch.object(docker, 'manifest') as publish:
            self.assertIsNone(docker.latest(self.root))
        publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
