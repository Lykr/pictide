"""Indeterminate ComfyUI readiness in the shared terminal frame."""
import time

from .terminal import Console, clean
from .text import translate


class StartupProgress:
    def __init__(self, log_path, *, stream=None, clock=time.monotonic):
        self.console = Console(stream=stream)
        self.clock, self.log_path = clock, log_path
        self.started = self.last = clock()
        self.done = False
        self.detail = ''

    @property
    def stream(self):
        return self.console.stream

    @property
    def animated(self):
        return self.console.interactive

    def _elapsed(self, now):
        elapsed = max(0, int(now - self.started))
        return f'{elapsed // 60:02d}:{elapsed % 60:02d}'

    def start(self):
        if not self.animated:
            self.console._write(translate('comfy_starting') + '\n'
                                + translate('startup_log', path=self.log_path) + '\n')
        self.tick(force=True)

    def tick(self, detail='', *, force=False):
        if self.done:
            return
        if detail:
            self.detail = clean(detail).replace('\n', ' ')[:400]
        now = self.clock()
        if not force and now - self.last < (.2 if self.animated else 5):
            return
        self.last = now
        message = translate('comfy_waiting', elapsed=self._elapsed(now))
        if self.animated:
            position = int(max(0, now - self.started) * 5) % 26
            position = position if position <= 13 else 26 - position
            bar = ' ' * position + '====' + ' ' * (13 - position)
            self.console.show(translate('comfy_starting'),
                [f'[{bar}]', message, '', self.detail, '', translate('startup_log', path=self.log_path)])
        else:
            self.console._write('  ' + message + (' · ' + self.detail if self.detail else '') + '\n')

    def finish(self, outcome):
        if self.done:
            return
        self.done = True
        message = translate('comfy_' + outcome, elapsed=self._elapsed(self.clock()))
        if self.animated:
            self.console.show(message, [self.detail, translate('startup_log', path=self.log_path)])
        else:
            self.console._write(message + '\n')
