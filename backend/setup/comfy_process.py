"""Owned ComfyUI process trees, clean external runtimes, and bounded logs."""
import codecs
from contextlib import contextmanager
import logging
import os
import signal
import subprocess
import sys
import threading
import time

from .comfy_discovery import probe
from ..desktop.startup_progress import StartupProgress
from ..desktop.terminal import ANIMATION_ENV, COLUMNS_ENV

log = logging.getLogger('backend.setup.local_generation')

class _WindowsJob:
    """Kill our ComfyUI tree if its owning Pictide process exits unexpectedly."""
    def __init__(self, process):
        import ctypes as c
        from ctypes import wintypes as w

        class Basic(c.Structure):
            _fields_ = [('process_time', c.c_longlong), ('job_time', c.c_longlong), ('flags', w.DWORD),
                        ('min_working_set', c.c_size_t), ('max_working_set', c.c_size_t),
                        ('active_processes', w.DWORD), ('affinity', c.c_size_t),
                        ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class IO(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in ('reads', 'writes', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]

        class Extended(c.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', c.c_size_t),
                        ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]

        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        self.kernel.SetInformationJobObject.restype = w.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = w.BOOL
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.CloseHandle.restype = w.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise c.WinError(c.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not (self.kernel.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits))
                and self.kernel.AssignProcessToJobObject(self.handle, int(process._handle))):
            error = c.get_last_error()
            self.close()
            raise c.WinError(error)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


@contextmanager
def external_runtime_dlls():
    """An embedded ComfyUI Python must load its own DLLs, not PyInstaller's."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    kernel.GetDllDirectoryW.restype = wintypes.DWORD
    kernel.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    kernel.SetDllDirectoryW.restype = wintypes.BOOL
    previous = ctypes.create_unicode_buffer(32768)
    kernel.GetDllDirectoryW(len(previous), previous)
    if not kernel.SetDllDirectoryW(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        kernel.SetDllDirectoryW(previous.value or None)


class _ManagedOutput:
    """Drain owned output into a bounded log and retain its latest startup line."""
    def __init__(self, pipe, target):
        from ..runtime_logging import make_log_handler

        self.pipe = pipe
        self.latest = ''
        self.logger = logging.Logger('backend.comfyui', level=logging.INFO)
        self.logger.propagate = False
        self.handler = make_log_handler(target)
        self.logger.addHandler(self.handler)
        self.thread = threading.Thread(target=self._read, name='pictide-comfyui-output', daemon=True)
        self.thread.start()

    def _read(self):
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        try:
            # ComfyUI may print progress with carriage returns or very long lines.
            # Limit each read so even output without newlines stays bounded.
            while chunk := self.pipe.readline(16 * 1024):
                message = decoder.decode(chunk).rstrip('\r\n')
                if message:
                    self.latest = message
                    self.logger.info('%s', message)
            trailing = decoder.decode(b'', final=True)
            if trailing:
                self.logger.info('%s', trailing)
        except (OSError, ValueError):
            log.exception('Could not read managed ComfyUI output')
        finally:
            self.pipe.close()
            self.logger.removeHandler(self.handler)
            self.handler.close()

    def close(self):
        # The owning process is stopped before joining; drain its final output.
        self.thread.join(timeout=5)


def external_environment():
    environment = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', '__PYVENV_LAUNCHER__',
                '_PYI_APPLICATION_HOME_DIR', '_PYI_ARCHIVE_FILE',
                '_PYI_PARENT_PROCESS_LEVEL', '_PYI_SPLASH_IPC', ANIMATION_ENV, COLUMNS_ENV):
        environment.pop(key, None)
    if getattr(sys, 'frozen', False) and sys.platform.startswith('linux'):
        original = environment.pop('LD_LIBRARY_PATH_ORIG', None)
        if original is None:
            environment.pop('LD_LIBRARY_PATH', None)
        else:
            environment['LD_LIBRARY_PATH'] = original
    environment.update(PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    return environment


class ComfyProcess:
    def __init__(self, paths):
        self.paths = paths
        self.process = self.job = self.output = None
        self.url = None
        self.stopping = threading.Event()
        self.lock = threading.RLock()

    def launch(self, command, cwd, url, *, headers=None, timeout=120):
        if self.process is not None:
            raise RuntimeError('ComfyUI is already owned by this session')
        self.url = url
        progress = StartupProgress(self.paths.logs / 'comfyui.log')
        progress.start()
        try:
            with self.lock:
                if self.stopping.is_set():
                    raise InterruptedError('ComfyUI startup was cancelled')
                with external_runtime_dlls():
                    self.process = subprocess.Popen(command, cwd=cwd, env=external_environment(),
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                        start_new_session=sys.platform != 'win32')
                process = self.process
                if sys.platform == 'win32':
                    self.job = _WindowsJob(process)
                self.output = _ManagedOutput(process.stdout, self.paths.logs / 'comfyui.log')
            log.info('Managed ComfyUI started, pid=%s, address=%s', process.pid, url)
            deadline, last = time.monotonic() + timeout, time.monotonic()
            while process.poll() is None:
                if self.stopping.is_set():
                    raise InterruptedError('ComfyUI startup was cancelled')
                if probe(url, headers=headers) is not None and not self.stopping.is_set() and process.poll() is None:
                    log.info('Managed ComfyUI ready at %s, pid=%s', url, process.pid)
                    progress.finish('ready')
                    return url
                if time.monotonic() >= deadline:
                    raise TimeoutError('ComfyUI startup timed out; see logs/comfyui.log')
                if time.monotonic() - last >= 10:
                    log.info('ComfyUI is still starting; see logs/comfyui.log')
                    last = time.monotonic()
                progress.tick(self.output.latest if self.output else '')
                time.sleep(.2)
            raise RuntimeError('ComfyUI could not start; see logs/comfyui.log')
        except BaseException as error:
            progress.finish('cancelled' if self.stopping.is_set() or isinstance(error, KeyboardInterrupt) else 'failed')
            self.close()
            raise

    def close(self):
        self.stopping.set()
        with self.lock:
            process = self.process
            if self.job is not None:
                self.job.close()
                self.job = None
            elif process is not None and sys.platform != 'win32':
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if process is not None:
                try:
                    if sys.platform == 'win32' and process.poll() is None:
                        process.terminate()
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                finally:
                    if sys.platform != 'win32':
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                if self.output is not None:
                    self.output.close()
                    self.output = None
                elif process.stdout is not None:
                    process.stdout.close()
                log.info('Managed ComfyUI exited, pid=%s, exit_code=%s', process.pid, process.returncode)
                self.process = None
