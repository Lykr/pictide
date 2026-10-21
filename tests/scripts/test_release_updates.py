import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backend import __version__
from scripts.release_updates import write_manifest


class ReleaseManifestTests(unittest.TestCase):
    def test_manifest_binds_native_checks_and_handles_windows_build_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = f'pictide-{__version__}-win32-amd64.zip'
            (root / name).write_bytes(b'verified native package')
            digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
            report = dict(passed=True, archive=name, version=__version__, updates_verified=True, archive_sha256=digest)
            (root / 'smoke-report-windows.json').write_text(json.dumps(report))
            (root / 'build-report-windows.json').write_text(json.dumps(dict(passed=True, archive='D:\\build\\releases\\' + name, unpacked_bytes=100)))
            manifest = write_manifest(root)
            self.assertIs(manifest['requires_data_migration'], False)
            self.assertEqual(manifest['assets']['win32-amd64']['sha256'], digest)
            self.assertTrue(manifest['assets']['win32-amd64']['install_verified'])
            policy = root / 'policy.json'
            policy.write_text(json.dumps(dict(schema=1, requires_data_migration=True,
                                             direct_upgrade_from=manifest['direct_upgrade_from'])))
            self.assertIs(write_manifest(root, policy)['requires_data_migration'], True)
            report.pop('updates_verified')
            (root / 'smoke-report-windows.json').write_text(json.dumps(report))
            self.assertFalse(write_manifest(root)['assets']['win32-amd64']['install_verified'])
            (root / name).write_bytes(b'changed package')
            with self.assertRaises(ValueError):
                write_manifest(root)
