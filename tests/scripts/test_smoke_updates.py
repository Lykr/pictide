import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.updates.releases import PAGE
from scripts.smoke_updates import download_previous


class PreviousReleaseTests(unittest.TestCase):
    def test_previous_package_is_pinned_to_the_platform_and_supported_source_range(self):
        content = b'previous native release'
        name = 'pictide-0.5.0-win32-amd64.zip'
        asset = dict(name=name, size=len(content), digest='sha256:' + hashlib.sha256(content).hexdigest(),
                     browser_download_url=PAGE + '/download/v0.5.0/' + name)
        document = dict(tag_name='v0.5.0', assets=[asset])
        with tempfile.TemporaryDirectory() as directory, patch('backend.__version__', '0.5.1'), \
             patch('scripts.smoke_updates.read_json', return_value=document), \
             patch('scripts.smoke_updates.open_url', return_value=io.BytesIO(content)) as opener:
            result = download_previous('pictide-0.5.1-win32-amd64.zip', Path(directory) / 'previous')
            self.assertEqual(result.read_bytes(), content)
            opener.assert_called_once_with(asset['browser_download_url'], timeout=60)
            opener.reset_mock()
            for tag in ('v0.5.1', 'v0.4.9'):
                document['tag_name'] = tag
                self.assertIsNone(download_previous('pictide-0.5.1-win32-amd64.zip', Path(directory) / tag))
            opener.assert_not_called()
