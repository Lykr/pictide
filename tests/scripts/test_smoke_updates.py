import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.updates.releases import API, PAGE
from scripts.smoke_updates import download_previous


class PreviousReleaseTests(unittest.TestCase):
    def test_ci_uses_authenticated_metadata_without_changing_local_downloads(self):
        document = dict(tag_name='v0.6.2')
        for actions, token, authenticated in (('true', 'test-token', True), ('true', '', False), ('false', 'test-token', False)):
            with self.subTest(actions=actions, authenticated=authenticated), tempfile.TemporaryDirectory() as directory, \
                    patch.dict(os.environ, GITHUB_ACTIONS=actions, GH_TOKEN=token), \
                    patch('backend.__version__', '0.6.2'), \
                    patch('scripts.smoke_updates.read_json', return_value=document) as anonymous, \
                    patch('scripts.smoke_updates.subprocess.check_output', return_value=json.dumps(document)) as authenticated_read:
                self.assertIsNone(download_previous('pictide-0.6.2-darwin-arm64.zip', Path(directory)))
                if authenticated:
                    authenticated_read.assert_called_once_with(['gh', 'api', API], text=True)
                    anonymous.assert_not_called()
                else:
                    anonymous.assert_called_once_with(API)
                    authenticated_read.assert_not_called()

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
