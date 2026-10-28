"""Keyboard navigation and one refreshed viewport across startup stages."""
import io
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.desktop.terminal import ANIMATION_ENV, COLUMNS_ENV, LINES_ENV, Console, clean, read_key, status, width
from backend.recommendation.resources import _progress as model_progress
from backend.setup.vocabulary import _progress as vocabulary_progress


class TerminalTests(unittest.TestCase):
    def test_arrows_enter_and_escape_are_the_only_menu_actions(self):
        console = Console(stream=io.StringIO(), interactive=True)
        keys = Mock(side_effect=['2', 'unknown', 'down', 'up', 'up', 'enter'])
        self.assertEqual(console.choose('Menu', ['one', 'two', 'three'], read=keys), 2)
        self.assertEqual(keys.call_count, 6)
        self.assertIsNone(console.choose('Menu', ['one'], read=lambda: 'escape'))

    def test_long_menu_keeps_selection_and_controls_visible_in_a_small_terminal(self):
        output = io.StringIO()
        options = [f'环境 {index} · local environment' for index in range(20)]
        with patch.dict(os.environ, {COLUMNS_ENV: '32', LINES_ENV: '12'}):
            result = Console(stream=output, interactive=True).choose('选择环境', options,
                ['A long hardware description that wraps over several terminal rows.'],
                read=Mock(side_effect=['down'] * 19 + ['enter']), keys='↑ ↓ 选择 · Enter 确认 · Esc 返回')
        self.assertEqual(result, 19)
        frame = clean(output.getvalue().rsplit('\x1b[H', 1)[1])
        self.assertIn('› 环境 19', frame)
        self.assertIn('Esc 返回', frame)
        self.assertLessEqual(len(frame.splitlines()), 11)
        self.assertTrue(all(width(line) <= 31 for line in frame.splitlines()))

    def test_path_editing_keeps_chinese_characters_and_supports_back_and_cancel(self):
        console = Console(stream=io.StringIO(), interactive=True)
        result = console.read_text('Directory', 'Path',
            read=Mock(side_effect=[*'E:/图x片', 'left', 'backspace', 'end', 'enter']))
        self.assertEqual(result, 'E:/图片')
        self.assertIsNone(console.read_text('Directory', 'Path', read=lambda: 'escape'))

    def test_model_and_vocabulary_progress_replace_the_same_screen_and_keep_file_log_events(self):
        output = io.StringIO()
        with patch.dict(os.environ, {ANIMATION_ENV: '1'}), patch('sys.stdout', output), \
                self.assertLogs('backend', level='INFO') as events:
            model_progress('MiniLM: 50%')
            vocabulary_progress('Vocabulary filtered: 75%')
        frame = clean(output.getvalue().rsplit('\x1b[H', 1)[1])
        self.assertIn('Vocabulary filtered: 75%', frame)
        self.assertNotIn('MiniLM', frame)
        self.assertEqual(len(events.records), 2)

    def test_all_ratings_notice_remains_visible_while_download_progress_refreshes(self):
        output = io.StringIO()
        with patch.dict(os.environ, {ANIMATION_ENV: '1'}), patch('sys.stdout', output):
            vocabulary_progress('all-ratings: 25%', notice='可能生成露骨内容')
            vocabulary_progress('all-ratings: 75%', notice='可能生成露骨内容')
        frame = clean(output.getvalue().rsplit('\x1b[H', 1)[1])
        self.assertIn('可能生成露骨内容', frame)
        self.assertIn('75%', frame)
        self.assertNotIn('25%', frame)

    def test_redirected_output_never_reads_keys_or_contains_terminal_controls(self):
        output = io.StringIO()
        with patch.dict(os.environ, {ANIMATION_ENV: '0'}), patch('sys.stdout', output), \
                patch('backend.desktop.terminal.read_key', side_effect=AssertionError('read redirected input')):
            status('Preparing dependency')
            self.assertIsNone(Console().choose('Menu', ['one']))
        self.assertEqual(output.getvalue(), 'Preparing dependency\n')

    def test_console_details_cannot_inject_frames_or_expose_tokens(self):
        output = io.StringIO()
        Console(stream=output, interactive=True).show('Status', ['\x1b[2Jtoken=private-token\x07'])
        frame = clean(output.getvalue())
        self.assertIn('token=[redacted]', frame)
        self.assertNotIn('private-token', frame)
        self.assertNotIn('\x07', frame)

    def test_windows_extended_key_is_consumed_as_one_action(self):
        keyboard = SimpleNamespace(getwch=Mock(side_effect=['\xe0', 'P', '\r']), kbhit=lambda: True)
        with patch('backend.desktop.terminal.os.name', 'nt'), patch.dict(sys.modules, {'msvcrt': keyboard}):
            self.assertEqual(read_key(), 'down')
            self.assertEqual(read_key(), 'enter')

    def test_posix_arrow_and_unicode_are_decoded_without_leaking_escape_bytes(self):
        keyboard = SimpleNamespace(encoding='utf-8', fileno=lambda: 11)
        with patch('backend.desktop.terminal.os.name', 'posix'), patch('sys.stdin', keyboard), \
                patch('os.read', side_effect=[b'\x1b', b'[', b'B', b'\xe5', b'\x9b', b'\xbe']), \
                patch('select.select', return_value=([11], [], [])):
            self.assertEqual(read_key(), 'down')
            self.assertEqual(read_key(), '图')


if __name__ == '__main__':
    unittest.main()
