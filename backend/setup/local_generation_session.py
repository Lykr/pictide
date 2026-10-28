"""Windows preparation decisions and ownership of a local ComfyUI service."""
import asyncio
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import socket
import tempfile

from ..desktop.text import system_language
from ..desktop.terminal import interactive_terminal, status
from .comfy_process import ComfyProcess, _WindowsJob

log = logging.getLogger('backend.setup.local_generation')


def announce(english, chinese):
    message = chinese if system_language() == 'zh-CN' else english
    log.info('%s', message)
    status(message)


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
    if not interactive_terminal():
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
    if not interactive_terminal():
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


class ManagedComfy(ComfyProcess):
    def __init__(self, paths, state):
        super().__init__(paths)
        self.state = dict(state)

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
        self.launch(command, install, self.url)
        self.state['port'] = port
        write_state(self.paths, self.state)
        return self.url

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
