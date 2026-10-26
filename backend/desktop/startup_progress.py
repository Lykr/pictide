"""Small indeterminate terminal view for the existing local-service startup output."""
import logging
import os
import re
import shutil
import sys
import time
import unicodedata

from .text import translate
from ..runtime_logging import RuntimeFormatter

ANIMATION_ENV = 'PICTIDE_STARTUP_ANIMATION'
COLUMNS_ENV = 'PICTIDE_STARTUP_COLUMNS'
_ANSI = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]')
_FORMATTER = RuntimeFormatter('%(message)s')


def _width(text):
    return sum(0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
               for char in text)


def _fit(text, columns):
    if _width(text) <= columns:
        return text
    result, used = [], 0
    for char in text:
        width = _width(char)
        if used + width > max(0, columns - 3):
            break
        result.append(char)
        used += width
    return ''.join(result) + '...'


def _detail(text):
    text = _ANSI.sub('', str(text))
    text = ''.join(char for char in text if char.isprintable())
    record = logging.LogRecord('comfyui-startup', logging.INFO, '', 0, text, (), None)
    return _FORMATTER.format(record)[:400]


class StartupProgress:
    def __init__(self, log_path, *, stream=None, clock=time.monotonic):
        self.stream = stream if stream is not None else sys.stdout
        self.clock, self.log_path = clock, log_path
        self.started = self.last = clock()
        self.drawn = 0
        self.done = False
        try:
            self.animated = bool(self.stream and self.stream.isatty())
        except (AttributeError, OSError, ValueError):
            self.animated = False
        if os.environ.get(ANIMATION_ENV) in ('0', '1'):
            self.animated = os.environ[ANIMATION_ENV] == '1'

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
            # Presentation must never decide whether the service can start.
            self.stream = None

    def _elapsed(self, now):
        elapsed = max(0, int(now - self.started))
        return f'{elapsed // 60:02d}:{elapsed % 60:02d}'

    def start(self):
        self._write(translate('comfy_starting') + '\n')
        self._write(translate('startup_log', path=self.log_path) + '\n')
        self.tick(force=True)

    def tick(self, detail='', *, force=False):
        if self.done:
            return
        now = self.clock()
        if not force and now - self.last < (.2 if self.animated else 5):
            return
        self.last = now
        message = translate('comfy_waiting', elapsed=self._elapsed(now))
        if detail:
            message += ' · ' + _detail(detail)
        if self.animated:
            position = int(max(0, now - self.started) * 5) % 26
            position = position if position <= 13 else 26 - position
            bar = ' ' * position + '====' + ' ' * (13 - position)
            try:
                columns = max(24, int(os.environ.get(COLUMNS_ENV) or shutil.get_terminal_size().columns))
            except (ValueError, OSError):
                columns = 80
            line = _fit(f'  [{bar}] {message}', columns - 1)
            padding = ' ' * max(0, self.drawn - _width(line))
            self._write('\r' + line + padding)
            self.drawn = _width(line)
        else:
            self._write('  ' + message + '\n')

    def finish(self, outcome):
        if self.done:
            return
        self.done = True
        if self.drawn:
            self._write('\r' + ' ' * self.drawn + '\r')
        self._write(translate('comfy_' + outcome, elapsed=self._elapsed(self.clock())) + '\n')
