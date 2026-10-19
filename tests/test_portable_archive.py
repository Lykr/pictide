"""Verify portable archives with native macOS framework links where available."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

from scripts.build_portable import write_archive
from scripts.smoke_portable import unpack


class PortableArchiveSmoke(unittest.TestCase):
    def test_regular_files_keep_package_root_and_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / 'Pictide'
            package.mkdir()
            (package / 'README.txt').write_text('portable fixture', encoding='utf-8')
            archive = root / 'portable.zip'
            write_archive(package, archive)
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(bundle.read('Pictide/README.txt'), b'portable fixture')

    @unittest.skipUnless(sys.platform == 'darwin', 'Requires the real macOS ditto tool')
    def test_native_roundtrip_preserves_python_framework_links_and_permissions(self):
        with tempfile.TemporaryDirectory(prefix='portable archive ') as temporary:
            root = Path(temporary)
            package = root / 'Pictide'
            runtime = package / 'data/runtime/pictide'
            internal = runtime / '_internal'
            version = internal / 'Python.framework/Versions/3.12'
            version.mkdir(parents=True)
            (version / 'Python').write_bytes(b'Python library fixture')
            (version / 'Python').chmod(0o755)
            (version.parent / 'Current').symlink_to('3.12', target_is_directory=True)
            (internal / 'Python.framework/Python').symlink_to('Versions/Current/Python')
            (internal / 'Python').symlink_to('Python.framework/Versions/3.12/Python')
            for path in (runtime / 'Pictide', package / 'start.command'):
                path.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
                path.chmod(0o755)
            archive = root / 'portable.zip'
            write_archive(package, archive)
            executable = unpack(archive, root / 'native extraction')
            restored = executable.parent / '_internal'
            self.assertEqual((restored / 'Python').read_bytes(), b'Python library fixture')
            self.assertEqual((restored / 'Python.framework/Python').read_bytes(), b'Python library fixture')
            self.assertEqual(os.readlink(restored / 'Python.framework/Versions/Current'), '3.12')
            self.assertTrue(os.access(executable, os.X_OK))


if __name__ == '__main__':
    unittest.main()
