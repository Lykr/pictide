"""Keep startup progress visible while the desktop service owns no console."""
import os
from pathlib import Path
import subprocess
import sys
import time

from .desktop_text import translate

STATUS_ENV = 'PICTIDE_DESKTOP_STATUS'


def notify_launcher(status):
    destination = os.environ.get(STATUS_ENV)
    if destination:
        Path(destination).write_text(status, encoding='utf-8')
        return True
    return False


def launch_desktop(arguments, paths):
    """Exit the progress process once its windowless child registers the tray.

    Return False only when the service needs the original terminal as fallback.
    Other successful exits include reopening an already-running instance.
    """
    name = f'desktop-startup-{time.time_ns()}'
    status = paths.tmp / (name + '.status')
    output = paths.tmp / (name + '.log')
    command = [sys.executable]
    if not getattr(sys, 'frozen', False):
        command += ['-m', 'backend.host']
    command += [*arguments, '--desktop-worker']
    environment = dict(os.environ, **{STATUS_ENV: str(status)})
    with output.open('w', encoding='utf-8') as stream:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream,
                                   stderr=subprocess.STDOUT, env=environment,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        with output.open(encoding='utf-8', errors='replace') as progress:
            while True:
                text = progress.read()
                if text:
                    print(text, end='', flush=True)
                state = status.read_text(encoding='utf-8') if status.exists() else ''
                if state == 'ready':
                    return True
                if process.poll() is not None:
                    print(progress.read(), end='', flush=True)
                    if state == 'console':
                        return False
                    if process.returncode:
                        if sys.stdin is not None and sys.stdin.isatty():
                            try:
                                input(translate('close_prompt'))
                            except EOFError:
                                pass
                        raise SystemExit(process.returncode)
                    return True
                time.sleep(0.1)
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise
    finally:
        status.unlink(missing_ok=True)
