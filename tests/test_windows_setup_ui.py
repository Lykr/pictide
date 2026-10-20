"""First-run choices, resumable retries and cancellation without downloads."""
import io
import unittest
from unittest.mock import Mock, patch

from backend.windows_setup_ui import _profile_from_device_ids, run_setup


PROFILES = {'nvidia': {'name': 'NVIDIA', 'size': 2_000_000_000}}
RECIPES = {'anima': {
    'name': 'Anima Turbo v1.1', 'size': 5_628_171_998,
    'license_name': 'CircleStone Labs Non-Commercial',
    'license_url': 'https://huggingface.co/circlestone-labs/Anima/blob/main/LICENSE.md',
    'noncommercial': True,
}}


class WindowsSetupUISmoke(unittest.TestCase):
    def test_gpu_vendor_priority_and_unknown_devices(self):
        self.assertEqual(_profile_from_device_ids([
            r'PCI\VEN_8086&DEV_A780', r'PCI\VEN_10de&DEV_2782']), 'nvidia')
        self.assertEqual(_profile_from_device_ids([
            r'PCI\VEN_8086&DEV_A780', r'PCI\VEN_1002&DEV_747E']), 'amd')
        self.assertEqual(_profile_from_device_ids([r'PCI\VEN_8086&DEV_A780']), 'intel')
        self.assertIsNone(_profile_from_device_ids([
            r'ROOT\BasicDisplay', r'PCI\VEN_1414&DEV_008C', 'unknown']))

    def run_choices(self, answers, install, *, language='en'):
        output = io.StringIO()
        with patch('backend.windows_setup_ui._console_mode') as mode, \
                patch('builtins.input', side_effect=answers), \
                patch('sys.stdout', output):
            mode.return_value.__enter__.return_value = False
            result = run_setup(PROFILES, RECIPES, install,
                               data_directory='C:/Pictide/data', language=language)
        return result, output.getvalue()

    def test_external_and_later_never_install(self):
        install = Mock()
        for choice, expected in [('1', 'external'), ('3', 'later')]:
            with self.subTest(choice=choice):
                result, _ = self.run_choices([choice], install)
                self.assertEqual(result, {'mode': expected})
        install.assert_not_called()

    def test_local_retry_keeps_selection_and_returns_installation(self):
        calls = []
        installation = {'mode': 'local', 'recipe_id': 'anima', 'ready': True}

        def install(profile, recipe, progress):
            calls.append((profile, recipe))
            progress({'phase': 'download', 'name': 'anima.safetensors',
                      'downloaded': 50, 'total': 100, 'speed': 10})
            if len(calls) == 1:
                raise OSError('Connection interrupted; partial file retained')
            progress({'phase': 'verify', 'name': 'anima.safetensors'})
            return installation

        result, output = self.run_choices(['2', '1', '1', '1', '1'], install)
        self.assertIs(result, installation)
        self.assertEqual(calls, [('nvidia', 'anima'), ('nvidia', 'anima')])
        self.assertIn('7.63 GB', output)
        self.assertIn(RECIPES['anima']['license_url'], output)
        self.assertIn('Model use: non-commercial', output)
        self.assertIn('50%', output)
        self.assertIn('Verifying', output)

    def test_cancellation_during_install_returns_without_marking_ready(self):
        def install(profile, recipe, progress):
            self.assertEqual((profile, recipe), ('nvidia', None))
            raise KeyboardInterrupt

        result, output = self.run_choices(['2', '1', '2', '1'], install, language='zh-CN')
        self.assertIsNone(result)
        self.assertIn('已取消准备，下次可以继续。', output)
        self.assertNotIn('文件已就绪', output)


if __name__ == '__main__':
    unittest.main()
