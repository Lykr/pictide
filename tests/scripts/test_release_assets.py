from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts import release_artifacts as artifacts


class ReleaseDownloadsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        version = '0.10.0'
        release = dict(commit='a' * 40, tag='v' + version, version=version, portable={}, docker={})
        for platform, suffix in artifacts.PLATFORMS.items():
            name = f'pictide-{version}-{suffix}.zip'
            (self.root / name).write_bytes(('native ' + platform).encode())
            release['portable'][platform] = dict(archive=name, sha256=artifacts.digest(self.root / name))
        for architecture in artifacts.ARCHITECTURES:
            name = f'pictide-{version}-linux-{architecture}-docker.tar.gz'
            (self.root / name).write_bytes(('docker ' + architecture).encode())
            release['docker'][architecture] = dict(archive=name, sha256=artifacts.digest(self.root / name))
        for path in artifacts.diagnostic_paths(self.root):
            artifacts.write(path, {'report': path.name})
        artifacts.write(self.root / 'release.json', release)
        artifacts.write(self.root / 'update.json', {'version': version, 'assets': release['portable']})
        (self.root / 'compose.yaml').write_text('services: {}\n')

    def test_compact_downloads_preserve_all_reports_and_ignore_unrelated_files(self):
        (self.root / 'unexpected.log').write_text('not a download')
        before = {path.name: path.read_bytes() for path in artifacts.diagnostic_paths(self.root)}
        downloads = artifacts.release_downloads(self.root)
        names = {path.name for path in downloads}
        self.assertEqual(len(names), 10)
        self.assertIn('update.json', names)
        self.assertIn('compose.yaml', names)
        self.assertNotIn('release.json', names)
        self.assertNotIn('unexpected.log', names)
        with zipfile.ZipFile(self.root / artifacts.DIAGNOSTICS) as archive:
            self.assertEqual({name: archive.read(name) for name in archive.namelist()}, before)
            self.assertIsNone(archive.testzip())
        checksums = dict(line.split('  ', 1)[::-1] for line in (self.root / 'SHA256SUMS').read_text().splitlines())
        self.assertEqual(set(checksums), names - {'SHA256SUMS'})
        for name, expected in checksums.items():
            self.assertEqual(artifacts.digest(self.root / name), expected)
        # Regeneration neither adds the diagnostics ZIP to itself nor hashes stale checksums.
        self.assertEqual({path.name for path in artifacts.release_downloads(self.root)}, names)

    def test_changed_download_cannot_be_published(self):
        path = next(self.root.glob('pictide-*.zip'))
        path.write_bytes(b'changed after verification')
        with self.assertRaisesRegex(ValueError, 'verified release artifact'):
            artifacts.release_downloads(self.root)

    def test_missing_report_does_not_create_a_partial_diagnostic_bundle(self):
        (self.root / 'source-docker-arm64.json').unlink()
        with self.assertRaisesRegex(ValueError, 'complete release diagnostics'):
            artifacts.release_downloads(self.root)
        self.assertFalse((self.root / artifacts.DIAGNOSTICS).exists())


if __name__ == '__main__':
    unittest.main()
