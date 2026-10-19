"""Display language and localized startup progress, without network access."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import desktop_text
from backend.recommand.resources import prepare_model


class DesktopTextSmoke(unittest.TestCase):
    def test_windows_display_language_takes_precedence_over_region_and_environment(self):
        with (patch.object(desktop_text.sys, 'platform', 'win32'),
              patch.dict(desktop_text.os.environ, {'LANG': 'zh_CN.UTF-8'})):
            for language_id, expected in ((0x0804, 'zh-CN'), (0x1004, 'zh-CN'),
                                          (0x0004, 'zh-CN'), (0x0409, 'en'),
                                          (0x0404, 'en'), (0x0C04, 'en'), (0x0411, 'en')):
                with self.subTest(language_id=language_id):
                    with patch.object(desktop_text, '_windows_ui_language', return_value=language_id):
                        self.assertEqual(desktop_text.system_language(), expected)
            with patch.object(desktop_text, '_windows_ui_language', side_effect=OSError('unavailable')):
                self.assertEqual(desktop_text.system_language(), 'en')

    def test_locale_fallback_and_dynamic_translation(self):
        with patch.object(desktop_text.sys, 'platform', 'linux'):
            for language, expected in (('zh_CN.UTF-8', 'zh-CN'), ('zh_SG', 'zh-CN'),
                                       ('zh-Hans', 'zh-CN'), ('en_US.UTF-8', 'en'),
                                       ('zh_TW', 'en'), ('zh_HK', 'en'), ('ja_JP', 'en')):
                with self.subTest(language=language):
                    with patch.dict(desktop_text.os.environ, {'LANG': language}, clear=True):
                        self.assertEqual(desktop_text.system_language(), expected)
                        self.assertEqual(desktop_text.translate('open'),
                                         '打开 Pictide' if expected == 'zh-CN' else 'Open Pictide')
            with (patch.dict(desktop_text.os.environ, {}, clear=True),
                  patch.object(desktop_text.locale, 'getlocale', side_effect=ValueError('unknown locale'))):
                self.assertEqual(desktop_text.system_language(), 'en')

    def test_catalogs_have_matching_keys_and_parameter_templates(self):
        parameters = dict(directory='/model', path='model.onnx', percent=50, received=1,
                          total=2, attempt=1, error='SHA-256 mismatch', address='http://localhost:8189')
        self.assertEqual(desktop_text._TEXT['en'].keys(), desktop_text._TEXT['zh-CN'].keys())
        for language in ('en', 'zh-CN'):
            with patch.object(desktop_text, 'system_language', return_value=language):
                for key in desktop_text._TEXT[language]:
                    with self.subTest(language=language, key=key):
                        self.assertTrue(desktop_text.translate(key, **parameters))
                self.assertIn('SHA-256', desktop_text.translate('model_failed', **parameters))

    def test_chinese_download_reports_progress_and_verified_completion(self):
        payload = b'small pinned model fixture'
        catalog = dict(source='fixture/model', revision='pinned', files=[dict(
            path='model.onnx', bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())])
        response = io.BytesIO(payload)
        response.status = 200
        response.headers = {}
        progress = []
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(desktop_text, 'system_language', return_value='zh-CN'),
              patch('backend.recommand.resources.urlopen', return_value=response)):
            prepare_model(directory, catalog=catalog, progress=progress.append)
            self.assertEqual((Path(directory) / 'model.onnx').read_bytes(), payload)
        self.assertTrue(progress[0].startswith('正在准备 MiniLM'))
        self.assertIn('正在下载 MiniLM：model.onnx', progress)
        self.assertTrue(any('100%' in message and '字节' in message for message in progress))
        self.assertIn('MiniLM 校验完成：model.onnx', progress)
        self.assertEqual(progress[-1], 'MiniLM 已就绪，正在启动 Pictide。')
