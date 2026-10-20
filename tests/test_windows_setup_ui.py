"""First-run choices, resumable retries and cancellation without downloads."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.windows_setup_ui import choose_data_directory, run_setup


PROFILES = {'nvidia': {'name': 'NVIDIA', 'size': 2_000_000_000}}
RECIPES = {'anima': {
    'name': 'Anima Turbo v1.1', 'size': 5_628_171_998,
    'license_name': 'CircleStone Labs Non-Commercial',
    'license_url': 'https://huggingface.co/circlestone-labs/Anima/blob/main/LICENSE.md',
    'noncommercial': True,
    'hardware': {'min_vram_gib': 8, 'min_ram_gib': 16, 'profiles': ('nvidia', 'nvidia-cu126', 'amd', 'intel')},
}}
HARDWARE = {'gpus': [{'profile': 'nvidia', 'name': 'NVIDIA GeForce RTX 4070 Ti',
                      'vram_bytes': 12 * 1024 ** 3}], 'ram_bytes': 32 * 1024 ** 3}


class WindowsSetupUISmoke(unittest.TestCase):
    def run_choices(self, answers, install, *, language='en', hardware=HARDWARE,
                    profiles=PROFILES, recipes=RECIPES):
        output = io.StringIO()
        with patch('backend.windows_setup_ui._console_mode') as mode, \
                patch('backend.windows_setup_ui.detect_hardware', return_value=hardware), \
                patch('builtins.input', side_effect=answers), \
                patch('sys.stdout', output):
            mode.return_value.__enter__.return_value = False
            result = run_setup(profiles, recipes, install, language=language)
        return result, output.getvalue()

    def test_directory_default_back_and_cancel_do_not_create_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            current = Path(temporary) / 'data'
            for answers, expected in [(['1'], str(current)), (['2', '', '1'], str(current)),
                                      (['0'], None), (['\x1b'], None), ([KeyboardInterrupt], None)]:
                with self.subTest(answers=answers), \
                        patch('backend.windows_setup_ui._console_mode') as mode, \
                        patch('builtins.input', side_effect=answers), \
                        patch('sys.stdout', io.StringIO()) as output:
                    mode.return_value.__enter__.return_value = False
                    self.assertEqual(choose_data_directory(current, language='en'), expected)
                    self.assertIn('Data location', output.getvalue())
                    self.assertNotIn('will not be moved', output.getvalue())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_directory_retry_rejects_relative_and_confirms_quoted_new_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            current = Path(temporary) / 'data'
            selected = Path(temporary) / 'new data'
            with patch('backend.windows_setup_ui._console_mode') as mode, \
                    patch('backend.windows_setup_ui.system_language', return_value='zh-CN'), \
                    patch('builtins.input', side_effect=['2', 'relative/data', '2', f'"{selected}"', '1']), \
                    patch('sys.stdout', io.StringIO()) as output:
                mode.return_value.__enter__.return_value = False
                self.assertEqual(choose_data_directory(current, error='目录不可写'), str(selected))
            displayed = output.getvalue()
            self.assertIn('数据保存位置', displayed)
            self.assertIn('目录不可写', displayed)
            self.assertIn('请输入绝对目录路径。', displayed)
            self.assertIn(str(selected), displayed)
            self.assertEqual(displayed.count('原目录的数据会保留在原处，不会自动迁移。'), 1)
            self.assertEqual(list(Path(temporary).iterdir()), [])

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
        self.assertNotIn('ComfyUI location', output)
        self.assertNotIn('Model location', output)
        self.assertNotIn('Data directory', output)
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

    def test_insufficient_or_unknown_hardware_never_calls_installer(self):
        cases = [
            ({'gpus': [dict(HARDWARE['gpus'][0], vram_bytes=4 * 1024 ** 3)], 'ram_bytes': HARDWARE['ram_bytes']}, 'VRAM'),
            ({'gpus': HARDWARE['gpus'], 'ram_bytes': 8 * 1024 ** 3}, 'RAM'),
            ({'gpus': [dict(HARDWARE['gpus'][0], vram_bytes=None)], 'ram_bytes': HARDWARE['ram_bytes']}, 'unknown'),
            ({'gpus': [], 'ram_bytes': None}, 'matching'),
            ({'gpus': [dict(HARDWARE['gpus'][0], vram_bytes=4 * 1024 ** 3)] * 2,
              'ram_bytes': HARDWARE['ram_bytes']}, 'VRAM'),
            ({'gpus': [dict(HARDWARE['gpus'][0], vram_bytes=size * 1024 ** 3) for size in (6,12)],
              'ram_bytes': HARDWARE['ram_bytes']}, 'VRAM'),
        ]
        for hardware, message in cases:
            with self.subTest(hardware=hardware):
                install = Mock()
                result, output = self.run_choices(['2','1','1','1','0','3'], install, hardware=hardware)
                self.assertEqual(result, {'mode': 'later'})
                self.assertIn(message, output)
                install.assert_not_called()

    def test_manual_environment_cannot_bypass_matching_card(self):
        install = Mock()
        profiles = dict(PROFILES, amd={'name':'AMD','size':1})
        result, output = self.run_choices(['2','2','2','1','1','0','3'], install, profiles=profiles)
        self.assertEqual(result, {'mode':'later'})
        self.assertIn('No graphics card matching', output)
        install.assert_not_called()

    def test_each_model_uses_its_own_requirements(self):
        recipes = dict(RECIPES, larger=dict(RECIPES['anima'], name='Larger model',
                       hardware=dict(RECIPES['anima']['hardware'], min_vram_gib=16)))
        install = Mock(return_value={'mode':'managed'})
        _, output = self.run_choices(['2','1','2','1','1','1'], install, recipes=recipes)
        install.assert_called_once()
        self.assertEqual(install.call_args.args[:2], ('nvidia','anima'))
        self.assertIn('requires 16 GB', output)


if __name__ == '__main__':
    unittest.main()
