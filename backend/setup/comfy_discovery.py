"""Read-only discovery of local ComfyUI Python installations and launch options."""
import ipaddress
import json
import os
from pathlib import Path
import shlex
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from ..domain import ValidationError

MAX_JSON = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def endpoint(config):
    if not config or config.get('kind', 'comfyui') != 'comfyui':
        raise ValidationError('请选择一个已保存的本机 ComfyUI 生图 API。')
    parsed = urlsplit(config.get('base_url', ''))
    try:
        local = parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        local = False
    if (not local or parsed.scheme != 'http' or parsed.path not in ('', '/')
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValidationError('随应用启停需要不带路径的本机 HTTP ComfyUI 地址。')
    try:
        port = parsed.port or 80
    except ValueError:
        raise ValidationError('ComfyUI 端口无效。') from None
    host = '127.0.0.1' if parsed.hostname == 'localhost' else parsed.hostname
    return urlunsplit(('http', parsed.netloc, '', '', '')), host, port


def probe(url, *, headers=None):
    """Return recognizable ComfyUI stats; connection absence is distinct from another service."""
    request = Request(url + '/system_stats', headers=headers or {})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=1) as response:
            content = response.read(MAX_JSON + 1)
            if len(content) > MAX_JSON:
                raise ValueError('ComfyUI system information is too large')
            data = json.loads(content)
            system = data.get('system') if isinstance(data, dict) else None
            if not isinstance(system, dict) or not any(key in system for key in ('comfyui_version', 'python_version', 'pytorch_version')):
                raise ValueError('The configured port does not provide a recognizable ComfyUI service')
            return data
    except HTTPError as error:
        error.close()
        raise ValueError(f'ComfyUI readiness check returned HTTP {error.code}; check the address and credentials') from None
    except URLError as error:
        if isinstance(error.reason, (ConnectionRefusedError, TimeoutError, OSError)):
            return None
        raise ValueError('Cannot check the configured ComfyUI address') from None
    except (TimeoutError, ConnectionError):
        return None
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError('The configured port does not return ComfyUI system information') from None


def read_json(path, default=None):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            return default
        return json.loads(raw)
    except (OSError, ValueError):
        return default


def arguments(value):
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value[:256]
    if not isinstance(value, str) or len(value) > 32768:
        return []
    if sys.platform != 'win32':
        try:
            return shlex.split(value)
        except ValueError:
            return []
    import ctypes as c
    from ctypes import wintypes as w
    shell, kernel = c.WinDLL('shell32'), c.WinDLL('kernel32')
    shell.CommandLineToArgvW.argtypes = [w.LPCWSTR, c.POINTER(c.c_int)]
    shell.CommandLineToArgvW.restype = c.POINTER(w.LPWSTR)
    kernel.LocalFree.argtypes = [c.c_void_p]
    kernel.LocalFree.restype = c.c_void_p
    count = c.c_int()
    argv = shell.CommandLineToArgvW('comfy ' + value, c.byref(count))
    if not argv:
        return []
    try:
        return [argv[index] for index in range(1, min(count.value, 257))]
    finally:
        kernel.LocalFree(argv)


def launch_arguments(values, host, port):
    """The selected API owns the listening endpoint; preserve model and hardware options."""
    cleaned, index = [], 0
    while index < len(values):
        value = values[index]
        name = value.partition('=')[0]
        if name in ('--listen', '--port'):
            if '=' not in value and index + 1 < len(values) and not values[index + 1].startswith('--'):
                index += 1
        elif name not in ('--auto-launch', '--disable-auto-launch'):
            cleaned.append(value)
        index += 1
    return [*cleaned, '--disable-auto-launch', '--listen', host, '--port', str(port)]


def layout(path, *, python='', entry='', cwd='', args=None):
    root = Path(path).expanduser().resolve()
    if root.is_file() and root.name == 'main.py':
        entry, root = str(root), root.parent
    main = Path(entry).expanduser().resolve() if entry else next(
        (item for item in (root / 'main.py', root / 'ComfyUI/main.py') if item.is_file()), None)
    if main is None or main.name != 'main.py' or not main.is_file():
        raise ValidationError('未找到 ComfyUI 的 main.py，请检查安装路径。')
    roots = list(dict.fromkeys((root, main.parent, main.parent.parent)))
    candidates = [base / 'python_embeded/python.exe' for base in roots]
    for base in roots:
        candidates += [base / name for name in ('.venv/Scripts/python.exe', 'venv/Scripts/python.exe',
                        '.venv/bin/python', 'venv/bin/python')]
    # Preserve a virtual environment's executable path, including POSIX symlinks.
    executable = Path(python).expanduser().absolute() if python else next((item for item in candidates if item.is_file()), None)
    if executable is None or not executable.is_file():
        raise ValidationError('未找到 ComfyUI 的 Python，请在高级配置中指定解释器。')
    work = Path(cwd).expanduser().resolve() if cwd else main.parent
    if not work.is_dir():
        raise ValidationError('ComfyUI 工作目录不存在。')
    options = list(args or [])
    if executable.parent.name == 'python_embeded' and '--windows-standalone-build' not in options:
        options.append('--windows-standalone-build')
    return dict(install_dir=str(root), python=str(executable), entry=str(main), cwd=str(work), args=options)


def desktop_roots():
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA') or Path.home() / 'AppData/Roaming')
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return [base / 'Comfy Desktop', base / 'ComfyUI']


def desktop_installations():
    for directory in desktop_roots():
        records = read_json(directory / 'installations.json', [])
        if not isinstance(records, list):
            continue
        settings = read_json(directory / 'settings.json', {})
        settings = settings if isinstance(settings, dict) else {}
        for record in records[:128]:
            if not isinstance(record, dict) or not isinstance(record.get('installPath'), str):
                continue
            options = arguments(record.get('launchArgs', []))
            identifier = record.get('id', '')
            if isinstance(identifier, str) and identifier and Path(identifier).name == identifier:
                model_paths = directory / 'instance-model-paths' / (identifier + '.yaml')
                if model_paths.is_file() and '--extra-model-paths-config' not in options:
                    options += ['--extra-model-paths-config', str(model_paths)]
            for name in ('input', 'output'):
                value = settings.get(name + 'Dir')
                if isinstance(value, str) and value and '--' + name + '-directory' not in options:
                    options += ['--' + name + '-directory', value]
            yield record['installPath'], options


def discover(paths, config, install_dir=''):
    url, _, _ = endpoint(config)
    headers = {'Authorization': 'Bearer ' + config['api_key']} if config.get('api_key') else {}
    try:
        stats = probe(url, headers=headers)
    except (ValueError, OSError):
        stats = None
    argv = stats.get('system', {}).get('argv', []) if stats else []
    argv = argv if isinstance(argv, list) and all(isinstance(value, str) for value in argv) else []
    legacy = read_json(paths.runtime / 'local-generation.json', {})
    legacy = legacy if isinstance(legacy, dict) else {}
    sources = []
    if legacy.get('mode') == 'managed' and legacy.get('install_dir'):
        options = ['--cpu'] if legacy.get('profile_id') == 'cpu' else []
        model_paths = paths.runtime / 'comfyui-model-paths.yaml'
        if model_paths.is_file():
            options += ['--extra-model-paths-config', str(model_paths)]
        options += ['--output-directory', str(paths.cache / 'comfyui-output')]
        sources.append((legacy['install_dir'], options, 'pictide'))
    sources.extend((root, options, 'desktop') for root, options in desktop_installations())
    if install_dir:
        selected = Path(install_dir).expanduser().resolve()
        sources = [(root, options, source) for root, options, source in sources
                   if selected == Path(root).resolve() or selected in Path(root).resolve().parents
                   or Path(root).resolve() in selected.parents]
        sources.append((install_dir, [], 'path'))
    else:
        if argv and Path(argv[0]).is_absolute():
            sources.append((str(Path(argv[0]).parent), [], 'running'))
        sources.extend((str(root), [], 'path') for root in (paths.runtime / 'comfyui', Path.home() / 'ComfyUI'))
    found, seen = [], set()
    for root, options, source in sources:
        try:
            item = layout(root, args=options)
            if argv:
                observed = Path(argv[0])
                for base in (Path(root), Path(item['entry']).parent):
                    if (observed if observed.is_absolute() else base / observed).resolve() == Path(item['entry']):
                        item.update(cwd=str(base), args=argv[1:])
                        break
            key = (os.path.normcase(item['python']), os.path.normcase(item['entry']))
            if key not in seen:
                seen.add(key)
                found.append(dict(item, source=source))
        except (OSError, ValueError):
            continue
    return {'candidates': found}
