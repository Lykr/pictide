"""Keep startup progress visible while the desktop service owns no console."""
import os
import codecs
import socket
from pathlib import Path
import subprocess
import sys
import time

from .text import translate
from ..runtime_logging import LOG_MAX_BYTES, close_application_log, finish_desktop_output, trim_startup_logs

STATUS_ENV = 'PICTIDE_DESKTOP_STATUS'


def reserve_desktop_socket(host, port):
    """Own the listening address before dependency preparation begins."""
    server = socket.socket(socket.AF_INET6 if host == '::1' else socket.AF_INET)
    try:
        if os.name != 'nt':
            # Match asyncio's Unix restart behavior after browser/SSE TIME_WAIT.
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        if os.name != 'nt':
            # Reuse-address must not let two preparing launchers reserve one port.
            # No HTTP responses are served until the application is initialized.
            server.listen(socket.SOMAXCONN)
    except BaseException:
        server.close()
        raise
    return server


def watch_desktop_parent():
    """A macOS app owns the write end of stdin; EOF also stops orphaned workers."""
    import signal
    import threading

    descriptor = sys.stdin.fileno()

    def watch():
        # A buffered stdin read holds Python's IO lock while the parent is alive.
        # Normal service shutdown must not wait for that daemon thread or abort
        # when the interpreter closes stdin. Read the inherited OS pipe directly.
        while os.read(descriptor, 4096):
            pass
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=watch, name='desktop-parent', daemon=True).start()


def notify_launcher(status):
    destination = os.environ.get(STATUS_ENV)
    if destination:
        if status == 'ready':
            finish_desktop_output()
        Path(destination).write_text(status, encoding='utf-8')
        return True
    return False


def read_startup_output(pipe):
    """Read only available bytes, including when a venv launcher keeps the pipe open."""
    import ctypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.PeekNamedPipe.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                                    ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
    available = ctypes.c_ulong()
    handle = msvcrt.get_osfhandle(pipe.fileno())
    if not kernel.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
        error = ctypes.get_last_error()
        if error == 109:  # The child closed the pipe.
            return b''
        raise ctypes.WinError(error)
    return os.read(pipe.fileno(), min(available.value, 65536)) if available.value else b''


def launch_desktop(arguments, paths):
    """Exit the progress process once its windowless child registers the tray.

    Return False only when the service needs the original terminal as fallback.
    Other successful exits include reopening an already-running instance.
    """
    name = f'desktop-startup-{time.time_ns()}'
    status = paths.tmp / (name + '.status')
    output = paths.tmp / f'desktop-output-{time.time_ns()}.log'
    trim_startup_logs(paths.tmp)
    command = [sys.executable]
    if not getattr(sys, 'frozen', False):
        command += ['-m', 'backend.host']
    command += [*arguments, '--data-dir', str(paths.root), '--desktop-worker']
    environment = dict(os.environ, **{STATUS_ENV: str(status)})
    close_application_log()
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, env=environment,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    succeeded = False
    try:
        with output.open('wb') as capture:
            decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
            def drain():
                chunk = read_startup_output(process.stdout)
                if chunk:
                    if capture.tell() + len(chunk) > LOG_MAX_BYTES:
                        capture.seek(0); capture.truncate()
                    capture.write(chunk); capture.flush()
                    print(decoder.decode(chunk), end='', flush=True)
                return chunk
            while True:
                drain()
                state = status.read_text(encoding='utf-8') if status.exists() else ''
                if state == 'ready':
                    succeeded = True
                    return True
                if process.poll() is not None:
                    while drain():
                        pass
                    if state == 'console':
                        succeeded = True
                        return False
                    if process.returncode:
                        if sys.stdin is not None and sys.stdin.isatty():
                            try:
                                input(translate('close_prompt'))
                            except EOFError:
                                pass
                        raise SystemExit(process.returncode)
                    succeeded = True
                    return True
                time.sleep(0.1)
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise
    finally:
        process.stdout.close()
        status.unlink(missing_ok=True)
        if succeeded:
            output.unlink(missing_ok=True)
        trim_startup_logs(paths.tmp)
