"""Optional local ComfyUI startup configuration and per-session process ownership."""
import json
import logging
import os
from pathlib import Path
import socket
import tempfile
import threading

from ..domain import ValidationError
from .comfy_discovery import discover, endpoint, layout, launch_arguments, probe, read_json
from .comfy_process import ComfyProcess
from .local_generation_session import ManagedComfy, read_state

log = logging.getLogger('backend.setup.local_generation')
FIELDS = ('enabled', 'backend_id', 'install_dir', 'python', 'entry', 'cwd', 'args')


def empty_config():
    return dict(enabled=False, backend_id='', install_dir='', python='', entry='', cwd='', args=[])


class LocalComfyLifecycle:
    def __init__(self, paths, backend, backends):
        self.paths, self.backend, self.backends = paths, backend, backends
        self.target = paths.runtime / 'comfyui-lifecycle.json'
        self.lock = threading.RLock()
        self.child = self.legacy = None
        self.phase, self.error, self.url = 'disabled', '', None
        self.active = None
        self.attempted = False
        self.closing = False

    def _config(self):
        if self.target.exists():
            data = read_json(self.target)
            if not isinstance(data, dict) or set(data) != set(FIELDS):
                raise ValidationError('ComfyUI 启停配置损坏，请重新保存。')
            self._fields(data)
            return data
        state = read_state(self.paths)
        if not state or state.get('mode') != 'managed':
            return empty_config()
        document = dict(empty_config(), enabled=True, backend_id=state.get('backend_id', ''),
                        install_dir=state.get('install_dir', ''))
        try:
            args = ['--extra-model-paths-config', str(self.paths.runtime / 'comfyui-model-paths.yaml'),
                    '--output-directory', str(self.paths.cache / 'comfyui-output')]
            if state.get('profile_id') == 'cpu':
                args.append('--cpu')
            document.update(layout(document['install_dir'], args=args))
        except (ValueError, OSError):
            pass
        return document

    @staticmethod
    def _fields(data):
        if 'enabled' in data and type(data['enabled']) is not bool:
            raise ValidationError('ComfyUI 随应用启停须为布尔值。')
        for key in FIELDS[1:-1]:
            value = data.get(key, '')
            if not isinstance(value, str) or len(value) > 32768 or any(char in value for char in ('\0', '\r', '\n')):
                raise ValidationError('ComfyUI 路径或连接标识无效。')
        values = data.get('args', [])
        if (not isinstance(values, list) or len(values) > 256
                or any(not isinstance(value, str) or any(char in value for char in ('\0', '\r', '\n')) for value in values)
                or sum(map(len, values)) > 32768):
            raise ValidationError('ComfyUI 启动参数须为字符串数组，且总长度不超过 32768。')

    def settings(self):
        with self.lock:
            try:
                config, config_error = self._config(), ''
            except (OSError, ValueError) as error:
                config, config_error = empty_config(), str(error)
            if self.phase == 'running' and self.child and self.child.process and self.child.process.poll() is not None:
                self.phase, self.error = 'failed', 'ComfyUI exited; see logs/comfyui.log'
            choices = []
            for item in self.backends():
                try:
                    endpoint(item)
                    choices.append({key: item.get(key, '') for key in ('id', 'name', 'base_url')})
                except ValueError:
                    pass
            return dict(config=config, choices=choices, can_configure=True,
                        restart_required=self.attempted and config != self.active,
                        status=dict(phase='failed' if config_error else self.phase, error=config_error or self.error,
                                    owned=bool(self.child and self.child.process and self.child.process.poll() is None),
                                    url=self.url, log_path=str(self.paths.logs / 'comfyui.log')))

    def save(self, payload):
        if not payload or set(payload) - set(FIELDS):
            raise ValidationError('ComfyUI 启停设置包含未知字段或为空。')
        self._fields(payload)
        with self.lock:
            try:
                document = self._config()
            except (OSError, ValueError):
                document = empty_config()
            document.update(payload)
            if document['enabled']:
                config = self.backend(document['backend_id'])
                endpoint(config)
                if not document['install_dir'] and not document['entry']:
                    candidates = discover(self.paths, config)['candidates']
                    if len(candidates) != 1:
                        raise ValidationError('请自动识别并选择 ComfyUI 安装，或手动指定路径。')
                    document.update({key: candidates[0][key] for key in FIELDS if key in candidates[0]})
                document.update(layout(document['install_dir'] or str(Path(document['entry']).parent),
                    python=document['python'], entry=document['entry'], cwd=document['cwd'], args=document['args']))
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.paths.runtime,
                        prefix='comfyui-lifecycle-', suffix='.part', delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(document, stream, ensure_ascii=False, indent=2)
                os.replace(temporary, self.target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return self.settings()

    def detect(self, payload):
        if set(payload) - {'backend_id', 'install_dir'}:
            raise ValidationError('ComfyUI 识别请求包含未知字段。')
        self._fields(payload)
        identifier = payload.get('backend_id', '')
        return discover(self.paths, self.backend(identifier), payload.get('install_dir', ''))

    def start(self):
        if self.attempted:
            return
        self.attempted = True
        try:
            self.active = self._config()
            if not self.active['enabled']:
                return
            self.phase = 'starting'
            # Preserve the first-run installer's complete model/workflow handoff.
            if not self.target.exists():
                state = read_state(self.paths)
                if state and state.get('mode') == 'managed':
                    self.legacy = ManagedComfy(self.paths, state)
                    config = self.backend(state.get('backend_id', ''))
                    if config:
                        url, _, _ = endpoint(config)
                        headers = {'Authorization': 'Bearer ' + config['api_key']} if config.get('api_key') else {}
                        if probe(url, headers=headers) is not None:
                            self.legacy.url = self.url = url
                            self.phase = 'external'
                            return
                    child = self.child = self.legacy
                    if self.closing:
                        child.close()
                    self.url = self.legacy.start()
                    self.phase = 'running'
                    return
            config = self.backend(self.active['backend_id'])
            url, host, port = endpoint(config)
            self.url = url
            headers = {'Authorization': 'Bearer ' + config['api_key']} if config.get('api_key') else {}
            if probe(url, headers=headers) is not None:
                self.phase = 'external'
                return
            document = layout(self.active['install_dir'], python=self.active['python'],
                              entry=self.active['entry'], cwd=self.active['cwd'], args=self.active['args'])
            # Refuse to launch over an occupied or still-starting listener.
            family = socket.AF_INET6 if ':' in host else socket.AF_INET
            with socket.socket(family) as listener:
                listener.bind((host, port))
            args = launch_arguments(document['args'], host, port)
            child = self.child = ComfyProcess(self.paths)
            if self.closing:
                child.close()
            self.url = child.launch([document['python'], '-s', document['entry'], *args],
                                        document['cwd'], url, headers=headers)
            self.phase = 'running'
        except Exception as error:
            if self.closing:
                self.error, self.phase = '', 'stopped'
                log.info('Local ComfyUI startup cancelled during Pictide shutdown')
            else:
                self.error, self.phase = str(error), 'failed'
                log.exception('Local ComfyUI startup failed; Pictide settings remain available')
            child = self.child
            if child:
                child.close()
                if self.child is child:
                    self.child = None

    async def configure(self, application, session):
        if self.legacy and self.phase in ('running', 'external'):
            try:
                await self.legacy.configure(application, session)
                self.active = self._config()
            except Exception as error:
                self.error, self.phase = str(error), 'failed'
                log.exception('Could not configure the prepared local connection')

    def close(self):
        self.closing = True
        child = self.child
        if child is not None:
            child.close()
            if self.child is child:
                self.child = None
        if self.phase == 'running':
            self.phase = 'stopped'
