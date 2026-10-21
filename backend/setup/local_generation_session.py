"""Windows preparation decisions and ownership of a local ComfyUI service."""
import asyncio
import codecs
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import ProxyHandler, build_opener

from ..desktop.text import system_language

log = logging.getLogger('backend.setup.local_generation')


def announce(english, chinese):
    message = chinese if system_language() == 'zh-CN' else english
    log.info('%s', message)
    print(message, flush=True)


def read_state(paths):
    target = paths.runtime / 'local-generation.json'
    return json.loads(target.read_text(encoding='utf-8')) if target.exists() else None


def write_state(paths, state):
    target = paths.runtime / 'local-generation.json'
    temporary = target.with_suffix('.json.part')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)


@contextmanager
def setup_lock(paths):
    import msvcrt
    with (paths.tmp / 'local-setup.lock').open('a+b') as stream:
        if not stream.tell():
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def desktop_busy(paths):
    """Use the existing desktop lock rather than treating an old PID as ownership."""
    import msvcrt
    target = paths.tmp / 'desktop.lock'
    if not target.exists():
        return False
    with target.open('r+b') as stream:
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return True
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    return False


def prepare_windows_data_directory(paths, *, force=False):
    """Confirm the resolved data root before runtime setup creates files there."""
    if desktop_busy(paths):
        if force:
            announce('Exit Pictide from the tray before running --setup.',
                     '请先从托盘退出 Pictide，再运行 --setup。')
            return None
        return paths
    if not (sys.stdin and sys.stdin.isatty()):
        if force:
            raise RuntimeError('--setup requires an interactive terminal')
        return paths
    from ..paths import DataPaths, remember_data_directory, saved_data_directory
    from .windows_ui import choose_data_directory
    if not force and saved_data_directory() == paths.root:
        return paths
    current, error = paths.root, None
    while True:
        selected = choose_data_directory(str(current), error=error)
        if selected is None:
            return None
        chosen = DataPaths(selected)
        if force and desktop_busy(chosen):
            error = ('请先从托盘退出此目录的 Pictide。' if system_language() == 'zh-CN'
                     else 'Exit Pictide for this directory from the tray first.')
            current = chosen.root
            continue
        try:
            chosen.ensure()
            with tempfile.NamedTemporaryFile(prefix='pictide-write-check-', dir=chosen.tmp):
                pass
            remember_data_directory(chosen.root)
        except OSError as failure:
            error = str(failure)
            current = chosen.root
            continue
        return chosen


def prepare_windows_setup(paths, *, force=False):
    """Prompt only in the interactive progress process, never its hidden worker."""
    if desktop_busy(paths):
        if force:
            announce('Exit Pictide from the tray before running --setup.',
                     '请先从托盘退出 Pictide，再运行 --setup。')
            return False
        return True
    if not (sys.stdin and sys.stdin.isatty()):
        if force:
            raise RuntimeError('--setup requires an interactive terminal')
        return True
    from ..store import Repository
    if not force and (read_state(paths) is not None or
                      (paths.database.exists() and Repository(paths.database).backends())):
        return True
    from .local_generation import prepare_local_comfy, profile_catalog, recipe_catalog
    from .windows_ui import run_setup
    with setup_lock(paths) as claimed:
        if not claimed:
            announce('Local setup is already open. Continue in that window.',
                     '本地准备已打开，请在原窗口中继续。')
            return False
        # Another preparation may have completed while this launcher was opening.
        if not force and read_state(paths) is not None:
            return True
        profiles = profile_catalog()
        choice = run_setup(profiles, recipe_catalog(),
                           lambda profile, recipe, progress: prepare_local_comfy(paths, profile, recipe, progress))
        if choice is None:
            return False
        previous = read_state(paths) or {}
        if choice.get('mode') == 'managed':
            choice['configured'] = False
            if previous.get('recipe_id') == choice.get('recipe_id'):
                for key in ('backend_id', 'port'):
                    if key in previous:
                        choice[key] = previous[key]
        write_state(paths, choice)
        return True


def available_port(preferred=8190):
    with socket.socket() as listener:
        try:
            listener.bind(('127.0.0.1', preferred))
        except OSError:
            listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


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
    """Drain one owned process into a bounded, independently rotating log."""
    def __init__(self, pipe, target):
        from ..runtime_logging import make_log_handler

        self.pipe = pipe
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
        self.thread.join()


class ManagedComfy:
    def __init__(self, paths, state):
        self.paths, self.state = paths, dict(state)
        self.process = self.job = self.output = None
        self.url = None

    def start(self):
        install = Path(self.state['install_dir']).resolve()
        if install != (self.paths.runtime / 'comfyui').resolve():
            raise ValueError('The managed ComfyUI must be inside the selected data directory')
        python = install / 'python_embeded/python.exe'
        entry = install / 'ComfyUI/main.py'
        if not python.is_file() or not entry.is_file():
            raise FileNotFoundError('ComfyUI is incomplete. Run Pictide.exe --setup to prepare it again.')
        port = available_port(self.state.get('port', 8190))
        self.url = f'http://127.0.0.1:{port}'
        model_paths = self.paths.runtime / 'comfyui-model-paths.yaml'
        model_paths.write_text(json.dumps({'pictide': {
            'base_path': str(self.paths.models / 'generation'), 'is_default': True,
            **{key: key for key in ('checkpoints', 'diffusion_models', 'text_encoders', 'vae', 'loras')},
        }}), encoding='utf-8')
        output = self.paths.cache / 'comfyui-output'
        output.mkdir(parents=True, exist_ok=True)
        command = [str(python), '-s', str(entry), '--windows-standalone-build', '--disable-auto-launch',
                   '--listen', '127.0.0.1', '--port', str(port), '--extra-model-paths-config', str(model_paths),
                   '--output-directory', str(output)]
        if self.state['profile_id'] == 'cpu':
            command.append('--cpu')
        environment = os.environ.copy()
        for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', '_PYI_APPLICATION_HOME_DIR',
                    '_PYI_ARCHIVE_FILE', '_PYI_PARENT_PROCESS_LEVEL', '_PYI_SPLASH_IPC'):
            environment.pop(key, None)
        environment['PYTHONIOENCODING'] = 'utf-8'
        environment['PYTHONUNBUFFERED'] = '1'
        announce('Starting local ComfyUI…', '正在启动本地 ComfyUI…')
        try:
            with external_runtime_dlls():
                self.process = subprocess.Popen(command, cwd=install, env=environment, stdin=subprocess.DEVNULL,
                                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if sys.platform == 'win32':
                self.job = _WindowsJob(self.process)
            self.output = _ManagedOutput(self.process.stdout, self.paths.logs / 'comfyui.log')
            log.info('Managed ComfyUI started, pid=%s, address=%s', self.process.pid, self.url)
            opener = build_opener(ProxyHandler({}))
            deadline = time.monotonic() + 120
            last = time.monotonic()
            while self.process.poll() is None:
                try:
                    with opener.open(self.url + '/system_stats', timeout=1) as response:
                        if response.status == 200 and 'system' in json.load(response):
                            self.state['port'] = port
                            write_state(self.paths, self.state)
                            log.info('Managed ComfyUI ready at %s, pid=%s', self.url, self.process.pid)
                            return self.url
                except (OSError, ValueError):
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError('ComfyUI startup timed out; see data/logs/comfyui.log')
                if time.monotonic() - last > 10:
                    announce('ComfyUI is still starting; see the startup log for details.',
                             'ComfyUI 正在启动，详情可查看启动日志。')
                    last = time.monotonic()
                time.sleep(.2)
            raise RuntimeError('ComfyUI could not start; see data/logs/comfyui.log')
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.job is not None:
            self.job.close()
            self.job = None
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.output is not None:
            self.output.close()
            self.output = None
        elif self.process is not None and self.process.stdout is not None:
            self.process.stdout.close()
        if self.process is not None:
            log.info('Managed ComfyUI exited, pid=%s, exit_code=%s', self.process.pid, self.process.returncode)
            self.process = None

    async def configure(self, application, session):
        """Use existing configuration contracts before bootstrap becomes reachable."""
        recipe = self.state.get('recipe_id')
        if not recipe:
            announce(f'ComfyUI ready: {self.url}. Add a model in ComfyUI, then connect it in Pictide.',
                     f'ComfyUI 已就绪：{self.url}。添加模型后，可在 Pictide 中配置生图 API。')
            return
        from .local_generation import model_connection
        draft = model_connection(recipe, self.url)
        identifier = self.state.get('backend_id')
        if not identifier:
            identifier = draft['id']
            number = 2
            while await asyncio.to_thread(application.storage.backend, identifier):
                identifier = f'{draft["id"]}-{number}'
                number += 1
            self.state['backend_id'] = identifier
            write_state(self.paths, self.state)
        previous = await asyncio.to_thread(application.storage.backend, identifier)
        if self.state.get('configured') and previous is None:
            # Deleting a previously installed connection is an explicit user choice.
            return
        initial = not self.state.get('configured')
        if previous and not initial:
            draft = dict(previous, base_url=self.url)
        draft['id'] = identifier
        application.tasks.connections.session = session
        check = await application.check_backend(identifier, draft)
        if not check.get('ok'):
            raise RuntimeError(check.get('message') or 'ComfyUI workflow preflight failed')
        if not previous or draft != previous:
            await application.save_backend(identifier, draft)
        if initial:
            roam = await asyncio.to_thread(application.roam.get)
            await application.roam_settings({'prefetch_count': roam['prefetch_count'], 'backend_id': identifier})
        self.state['configured'] = True
        write_state(self.paths, self.state)
        announce('Local generation is ready. Open Pictide and start roaming.',
                 '本地生图已就绪，进入 Pictide 后即可开始漫游。')
