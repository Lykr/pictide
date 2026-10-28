"""Shared terminal frames and keyboard navigation; redirected output stays plain."""
import codecs
from contextlib import contextmanager
import logging
import os
import re
import shutil
import sys
import unicodedata

from .text import translate
from ..runtime_logging import RuntimeFormatter

ANIMATION_ENV = 'PICTIDE_STARTUP_ANIMATION'
COLUMNS_ENV = 'PICTIDE_STARTUP_COLUMNS'
LINES_ENV = 'PICTIDE_STARTUP_LINES'
_ANSI = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]')
_FORMATTER = RuntimeFormatter('%(message)s')


def _isatty(stream):
    try:
        return stream is not None and stream.isatty() is True
    except (AttributeError, OSError, ValueError):
        return False


def interactive_terminal():
    return _isatty(sys.stdin) and _isatty(sys.stdout)


def width(text):
    return sum(0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
               for char in text)


def clean(text):
    text = _ANSI.sub('', str(text))
    text = ''.join(char for char in text if char.isprintable() or char == '\n')
    return _FORMATTER.format(logging.LogRecord('terminal', logging.INFO, '', 0, text, (), None))


def _wrap(text, columns):
    lines = []
    for paragraph in clean(text).split('\n'):
        line, used = '', 0
        for char in paragraph:
            size = width(char)
            if used + size > columns:
                lines.append(line)
                line, used = '', 0
            line += char
            used += size
        lines.append(line)
    return lines


def _controls(text, columns):
    """Keep a key and its action together when the footer wraps."""
    lines, line = [], ''
    for part in re.split(r'\s*·\s*|\s{3,}', clean(text)):
        candidate = line + (' · ' if line else '') + part
        if line and width(candidate) > columns:
            lines.extend(_wrap(line, columns))
            line = part
        else:
            line = candidate
    return [*lines, *_wrap(line, columns)]


@contextmanager
def _output_mode(stream):
    """Enable ANSI while writing to an actual Windows console handle."""
    restore = lambda: None
    if os.name == 'nt' and _isatty(stream):
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        try:
            handle = msvcrt.get_osfhandle(stream.fileno())
            previous = wintypes.DWORD()
            if kernel.GetConsoleMode(handle, ctypes.byref(previous)) and kernel.SetConsoleMode(handle, previous.value | 4):
                restore = lambda: kernel.SetConsoleMode(handle, previous.value)
        except (AttributeError, OSError, ValueError):
            pass
    try:
        yield
    finally:
        restore()


@contextmanager
def console_mode():
    """Restore console modes and cursor even when input or setup is cancelled."""
    if not interactive_terminal():
        yield False
        return
    restore = lambda: None
    if os.name != 'nt':
        import termios
        import tty
        descriptor = sys.stdin.fileno()
        previous = termios.tcgetattr(descriptor)
        tty.setcbreak(descriptor)
        restore = lambda: termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)
    try:
        with _output_mode(sys.stdout):
            sys.stdout.write('\x1b[?25l')
            sys.stdout.flush()
            try:
                yield True
            finally:
                sys.stdout.write('\x1b[?25h')
                sys.stdout.flush()
    finally:
        restore()


def read_key(*, block=True):
    """Consume a whole key, including Windows prefixes and POSIX escape sequences."""
    if os.name == 'nt':
        import msvcrt
        if not block and not msvcrt.kbhit():
            return None
        key = msvcrt.getwch()
        if key in ('\x00', '\xe0'):
            return {'H': 'up', 'P': 'down', 'K': 'left', 'M': 'right', 'G': 'home', 'O': 'end',
                    'S': 'delete'}.get(msvcrt.getwch(), 'unknown')
    else:
        import select
        descriptor = sys.stdin.fileno()
        if not block and not select.select([descriptor], [], [], 0)[0]:
            return None
        decoder = codecs.getincrementaldecoder(sys.stdin.encoding or 'utf-8')(errors='replace')
        key = ''
        while not key:
            value = os.read(descriptor, 1)
            if not value:
                return 'eof'
            key = decoder.decode(value)
        if key == '\x1b':
            sequence = ''
            while len(sequence) < 8 and select.select([descriptor], [], [], .03)[0]:
                sequence += os.read(descriptor, 1).decode('ascii', errors='replace')
                if len(sequence) > 1 and (sequence[-1:].isalpha() or sequence.endswith('~')):
                    break
            if sequence:
                return {'[A': 'up', '[B': 'down', '[C': 'right', '[D': 'left', '[H': 'home', '[F': 'end',
                        'OH': 'home', 'OF': 'end', '[3~': 'delete'}.get(sequence, 'unknown')
    if key == '\x03':
        raise KeyboardInterrupt
    return {'\r': 'enter', '\n': 'enter', '\x1b': 'escape', '\x08': 'backspace',
            '\x7f': 'backspace', '\x04': 'eof'}.get(key, key)


class Console:
    def __init__(self, *, stream=None, interactive=None):
        self.stream = sys.stdout if stream is None else stream
        if interactive is None:
            forwarded = os.environ.get(ANIMATION_ENV)
            interactive = forwarded == '1' if forwarded in ('0', '1') else _isatty(self.stream)
        self.interactive = interactive
        self.drawn = False

    def _write(self, value):
        if self.stream is None:
            return
        try:
            try:
                self.stream.write(value)
            except UnicodeEncodeError:
                encoding = getattr(self.stream, 'encoding', None) or 'ascii'
                self.stream.write(value.encode(encoding, errors='replace').decode(encoding))
            self.stream.flush()
        except (OSError, ValueError):
            self.stream = None

    def show(self, heading, lines=(), *, footer='', focus=0):
        if not self.interactive:
            self._write('\n'.join(clean(line) for line in (heading, *lines) if line) + '\n')
            return
        size = shutil.get_terminal_size()
        try:
            columns = max(12, int(os.environ.get(COLUMNS_ENV) or size.columns)) - 3
            rows = max(8, int(os.environ.get(LINES_ENV) or size.lines)) - 1
        except ValueError:
            columns, rows = 77, 23
        header = _wrap('Pictide · ' + heading, columns)
        tail = _controls(footer, columns) if footer else []
        content, boundaries, focused = [], [], 0
        for index, line in enumerate(lines):
            boundaries.append(len(content))
            if index == focus:
                focused = len(content)
            content.extend(_wrap(line, columns))
        room = max(1, rows - len(header) - len(tail) - 3)
        if len(content) > room:
            start = max(0, min(focused - room // 2, len(content) - room))
            start = min((boundary for boundary in boundaries if start <= boundary <= focused), default=start)
            content = content[start:start + room]
        frame = ['', *header, '', *content, '', *tail]
        # Erase the previous viewport without appending to the terminal history.
        with _output_mode(self.stream):
            self._write(('\x1b[2J' if not self.drawn else '') + '\x1b[H'
                        + '\r\n'.join(('  ' + line if line else '') + '\x1b[K' for line in frame[:rows]) + '\x1b[J')
        self.drawn = True

    def choose(self, heading, options, details=(), *, read=None, keys=None):
        if read is None and not interactive_terminal():
            return None
        selected = 0
        while True:
            labels = [('› ' if index == selected else '  ') + label for index, label in enumerate(options)]
            self.show(heading, (*details, '', *labels), footer=keys or translate('terminal_keys'),
                      focus=len(details) + 1 + selected)
            key = (read or read_key)()
            if key in ('up', 'down'):
                selected = (selected + (-1 if key == 'up' else 1)) % len(options)
            elif key == 'enter':
                return selected
            elif key in ('escape', 'eof'):
                return None

    def read_text(self, heading, prompt, details=(), *, read=None):
        if read is None and not interactive_terminal():
            return None
        value, cursor = '', 0
        while True:
            self.show(heading, (*details, '', prompt, '› ' + value[:cursor] + '│' + value[cursor:]),
                      footer=translate('terminal_text_keys'), focus=len(details) + 2)
            key = (read or read_key)()
            if key in ('escape', 'eof'):
                return None
            if key == 'enter':
                return value
            if key == 'backspace' and cursor:
                value, cursor = value[:cursor - 1] + value[cursor:], cursor - 1
            elif key == 'delete':
                value = value[:cursor] + value[cursor + 1:]
            elif key == 'left':
                cursor = max(0, cursor - 1)
            elif key == 'right':
                cursor = min(len(value), cursor + 1)
            elif key == 'home':
                cursor = 0
            elif key == 'end':
                cursor = len(value)
            elif len(key) == 1 and key.isprintable():
                value, cursor = value[:cursor] + key + value[cursor:], cursor + 1


def status(message, *, heading=None, stream=None, details=()):
    """Use the same frame for startup resources, lifecycle notices and CLI progress."""
    console = Console(stream=stream)
    if console.interactive:
        console.show(heading or translate('starting'), [*details, message])
    else:
        console._write(clean(message) + '\n')


def close_prompt(message):
    """Keep a failed launch visible and use the same Enter/Esc confirmation."""
    if interactive_terminal():
        try:
            with console_mode():
                Console().choose(translate('terminal_error'), [translate('exit')], [message])
        except (EOFError, KeyboardInterrupt):
            pass
