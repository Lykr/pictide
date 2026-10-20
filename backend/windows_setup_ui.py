"""Dependency-free first-run console choices and installation progress."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sys
import time

from backend.desktop_text import system_language


_TEXT = {
    'en': {
        'title': 'Welcome to Pictide', 'question': 'How would you like to generate images?',
        'external': 'I already have an image generation API',
        'local': 'Set up local ComfyUI for me', 'later': 'Set up later',
        'keys': 'Up / Down: select   Enter: continue   Esc: back',
        'number': 'Choose a number (Enter / 0: back): ',
        'gpu': 'Prepare local image generation',
        'detected': 'Detected: {name}. Pictide can prepare the matching ComfyUI environment.',
        'use_detected': 'Use the recommended environment ({name})',
        'choose_other': 'Choose another environment',
        'gpu_manual': 'Choose a local generation environment',
        'gpu_help': 'Choose your graphics card brand, or CPU if you are not using a supported graphics card.',
        'gpu_unknown': 'Your graphics card could not be identified automatically.',
        'compatibility': 'NVIDIA standard uses CUDA 13.0; compatibility uses CUDA 12.6. Try compatibility if you encounter CUDA or driver compatibility problems.',
        'profile_nvidia': 'NVIDIA (standard)',
        'profile_nvidia-cu126': 'NVIDIA (compatibility · CUDA 12.6)',
        'profile_amd': 'AMD', 'profile_intel': 'Intel', 'profile_cpu': 'CPU (slow)',
        'model': 'Choose an image generation model', 'only': 'Skip model download — install ComfyUI only',
        'recommended': 'Recommended', 'review': 'Ready to download',
        'download': 'Total download', 'environment_download': 'Environment download',
        'model_download': 'Model download',
        'download_help': 'Download sizes are not VRAM requirements. Installation needs more disk space after extraction.',
        'data': 'Data directory', 'environment': 'ComfyUI location',
        'model_location': 'Model location', 'license': 'Model license',
        'license_note': 'Model use: non-commercial. Generated images may be used commercially.',
        'space': 'Reserve about {size} of free disk space.',
        'start': 'Download and prepare', 'back': 'Back',
        'preparing': 'Preparing local generation',
        'cancel': 'Esc / Ctrl+C: cancel; downloaded data is kept for resuming.',
        'cancelled': 'Preparation cancelled. You can resume next time.',
        'failed': 'Preparation could not finish', 'retry': 'Retry / resume',
        'success': 'Installation complete. Starting the local image service…',
        'only_success': 'Installation complete. Starting ComfyUI; add a model in Pictide next.',
        'download_phase': 'Downloading', 'verify_phase': 'Verifying',
        'extract_phase': 'Extracting', 'install_phase': 'Installing',
        'start_phase': 'Starting', 'ready_phase': 'Ready',
    },
    'zh-CN': {
        'title': '欢迎使用 Pictide', 'question': '你准备如何生成图片？',
        'external': '我已有生图 API', 'local': '帮我安装本地 ComfyUI', 'later': '稍后配置',
        'keys': '↑ ↓ 选择 · Enter 继续 · Esc 返回',
        'number': '输入选项编号（Enter / 0 返回）：',
        'gpu': '准备本地生图环境',
        'detected': '检测到 {name}，可以为你准备对应的 ComfyUI 运行环境。',
        'use_detected': '使用推荐环境（{name}）', 'choose_other': '选择其他环境',
        'gpu_manual': '选择本地生图环境',
        'gpu_help': '按显卡品牌选择；没有可用显卡时，可以使用 CPU。',
        'gpu_unknown': '未能自动识别显卡，请手动选择。',
        'compatibility': 'NVIDIA 标准环境使用 CUDA 13.0；兼容环境使用 CUDA 12.6，遇到 CUDA 或驱动兼容问题时可尝试。',
        'profile_nvidia': 'NVIDIA（标准环境）',
        'profile_nvidia-cu126': 'NVIDIA（兼容环境 · CUDA 12.6）',
        'profile_amd': 'AMD', 'profile_intel': 'Intel', 'profile_cpu': 'CPU（速度较慢）',
        'model': '选择生图模型',
        'only': '暂不下载模型，仅安装 ComfyUI', 'recommended': '推荐',
        'review': '准备下载', 'download': '预计下载合计',
        'environment_download': '环境下载', 'model_download': '模型下载',
        'download_help': '这里是下载体积，不是显存要求；解压安装后会占用更多磁盘空间。',
        'data': '数据目录',
        'environment': 'ComfyUI 位置', 'model_location': '模型位置', 'license': '模型许可',
        'license_note': '模型限非商业用途；生成图片可商用。',
        'space': '请预留约 {size} 可用磁盘空间。',
        'start': '下载并准备', 'back': '返回', 'preparing': '正在准备本地生图',
        'cancel': 'Esc / Ctrl+C 取消；保留已下载数据，下次可继续。',
        'cancelled': '已取消准备，下次可以继续。', 'failed': '准备未能完成',
        'retry': '重试 / 继续下载', 'success': '安装完成，正在启动本地生图服务…',
        'only_success': '安装完成，正在启动 ComfyUI；随后可在 Pictide 添加模型。',
        'download_phase': '下载', 'verify_phase': '校验', 'extract_phase': '解压',
        'install_phase': '安装', 'start_phase': '启动', 'ready_phase': '就绪',
    },
}


def _size(value):
    amount = float(value or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if amount < 1000 or unit == 'TB':
            return f'{amount:.2f} {unit}' if unit != 'B' else f'{amount:.0f} B'
        amount /= 1000


def _profile_from_device_ids(device_ids):
    vendors = set()
    for device_id in device_ids:
        if not device_id.upper().startswith('PCI\\'):
            continue
        vendor = re.search(r'\\VEN_([0-9A-F]{4})(?:&|$)', device_id.upper())
        if vendor:
            vendors.add(vendor.group(1))
    return next((profile for vendor, profile in (
        ('10DE', 'nvidia'), ('1002', 'amd'), ('8086', 'intel')) if vendor in vendors), None)


def detect_gpu_profile() -> str | None:
    """Read Windows display-adapter PCI IDs to suggest a user-adjustable profile."""
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes

    class DisplayDevice(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('DeviceName', wintypes.WCHAR * 32),
                    ('DeviceString', wintypes.WCHAR * 128), ('StateFlags', wintypes.DWORD),
                    ('DeviceID', wintypes.WCHAR * 128), ('DeviceKey', wintypes.WCHAR * 128)]

    try:
        enum = ctypes.WinDLL('user32', use_last_error=True).EnumDisplayDevicesW
        enum.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                         ctypes.POINTER(DisplayDevice), wintypes.DWORD]
        enum.restype = wintypes.BOOL
        device_ids = []
        index = 0
        while True:
            device = DisplayDevice()
            device.cb = ctypes.sizeof(device)
            if not enum(None, index, ctypes.byref(device), 0):
                break
            device_ids.append(device.DeviceID)
            index += 1
        return _profile_from_device_ids(device_ids)
    except (AttributeError, OSError):
        return None


@contextmanager
def _console_mode():
    """Enable ANSI for this console handle only and restore its original mode."""
    if os.name != 'nt' or not sys.stdin or not sys.stdout:
        yield False
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        yield False
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetConsoleMode.restype = wintypes.BOOL
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.SetConsoleMode.restype = wintypes.BOOL
    handle = kernel.GetStdHandle(-11 & 0xffffffff)
    previous = wintypes.DWORD()
    enabled = bool(kernel.GetConsoleMode(handle, ctypes.byref(previous))
                   and kernel.SetConsoleMode(handle, previous.value | 4))
    try:
        yield enabled
    finally:
        if enabled:
            kernel.SetConsoleMode(handle, previous.value)


class _Console:
    def __init__(self, text, interactive):
        self.text = text
        self.interactive = interactive
        self.last_progress = 0.0
        self.last_phase = None

    def show(self, heading, lines=()):
        if self.interactive:
            print('\x1b[2J\x1b[H', end='')
        print(f'\n  Pictide · {heading}\n')
        for line in lines:
            print(f'  {line}')
        print(flush=True)

    def choose(self, heading, options, details=()):
        if not self.interactive:
            self.show(heading, details)
            for index, label in enumerate(options, 1):
                print(f'  {index}. {label}')
            while True:
                answer = input('\n  ' + self.text['number']).strip()
                if not answer or answer == '0':
                    return None
                if answer.isdigit() and 1 <= int(answer) <= len(options):
                    return int(answer) - 1
        import msvcrt
        selected = 0
        while True:
            self.show(heading, (*details, '', *[
                ('› ' if index == selected else '  ') + label
                for index, label in enumerate(options)], '', self.text['keys']))
            key = msvcrt.getwch()
            if key in ('\x00', '\xe0'):
                direction = msvcrt.getwch()
                if direction in ('H', 'P'):
                    selected = (selected + (-1 if direction == 'H' else 1)) % len(options)
            elif key in ('\r', '\n'):
                return selected
            elif key == '\x1b':
                return None
            elif key == '\x03':
                raise KeyboardInterrupt
            elif key.isdigit() and 1 <= int(key) <= len(options):
                return int(key) - 1

    def progress(self, event):
        if self.interactive:
            import msvcrt
            while msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ('\x1b', '\x03'):
                    raise KeyboardInterrupt
        now = time.monotonic()
        phase = str(event.get('phase', 'download'))
        name = str(event.get('name', ''))
        downloaded = event.get('downloaded', 0) or 0
        total = event.get('total', 0) or 0
        interval = 0.2 if self.interactive else 5.0
        phase_key = (phase, name)
        if phase_key == self.last_phase and now - self.last_progress < interval:
            if not total or downloaded < total:
                return
        self.last_phase, self.last_progress = phase_key, now
        title = self.text.get(phase + '_phase', phase)
        lines = [f'{title}  {name}']
        if total:
            fraction = min(1, max(0, downloaded / total))
            width = 28
            filled = int(width * fraction)
            lines.append(f'[{"#" * filled}{"-" * (width - filled)}] {fraction:.0%}')
            lines.append(f'{_size(downloaded)} / {_size(total)}')
        elif downloaded:
            lines.append(_size(downloaded))
        if event.get('speed'):
            lines[-1] += f'  ·  {_size(event["speed"])}/s'
        lines.extend(('', self.text['cancel']))
        if self.interactive:
            self.show(self.text['preparing'], lines)
        else:
            print('  ' + ' · '.join(lines[:-2]), flush=True)


def _catalog_size(entry):
    if entry.get('size') is not None:
        return entry['size']
    return sum(item.get('size', 0) for item in entry.get('files', ()))


def _choose_profile(console, profiles, detected):
    text = console.text
    if detected:
        name = profiles[detected]['name']
        choice = console.choose(text['gpu'], [text['use_detected'].format(name=name), text['choose_other']],
                                [text['detected'].format(name=name)])
        if choice is None:
            return None
        if choice == 0:
            return detected
    details = [text['gpu_help'], text['compatibility']]
    if not detected:
        details.insert(0, text['gpu_unknown'])
    identifiers = list(profiles)
    index = console.choose(text['gpu_manual'], [
        text.get('profile_' + key, entry['name']) for key, entry in profiles.items()], details)
    return identifiers[index] if index is not None else None


def _run(console, profiles, recipes, install, data_directory):
    text = console.text
    detected = detect_gpu_profile()
    if detected not in profiles:
        detected = None
    while True:
        mode = console.choose(text['title'], [text['external'], text['local'], text['later']],
                              [text['question']])
        if mode is None:
            return None
        if mode != 1:
            return {'mode': 'external' if mode == 0 else 'later'}
        profile_id = _choose_profile(console, profiles, detected)
        if profile_id is None:
            continue
        profile = profiles[profile_id]
        recipe_ids = list(recipes)
        model = console.choose(text['model'], [
            f'{entry["name"]} · {text["model_download"]}: {_size(_catalog_size(entry))}'
            + (f' · {text["recommended"]}' if index == 0 else '')
            for index, entry in enumerate(recipes.values())] + [text['only']])
        if model is None:
            continue
        recipe_id = recipe_ids[model] if model < len(recipe_ids) else None
        recipe = recipes.get(recipe_id, {})
        size = _catalog_size(profile) + _catalog_size(recipe)
        required_space = profile.get('required_space', _catalog_size(profile) * 4) + _catalog_size(recipe)
        directory = Path(data_directory)
        details = [text.get('profile_' + profile_id, profile['name']) + (' + ' + recipe['name'] if recipe else ''),
                   f'{text["environment_download"]}: {_size(_catalog_size(profile))}']
        if recipe:
            details.append(f'{text["model_download"]}: {_size(_catalog_size(recipe))}')
        details.extend([
                   f'{text["download"]}: {_size(size)}',
                   text['download_help'], '',
                   f'{text["environment"]}: {directory / "runtime" / "comfyui"}'])
        if recipe:
            details.append(f'{text["model_location"]}: {directory / "models" / "generation"}')
        if recipe.get('license_name'):
            details.append(f'{text["license"]}: {recipe["license_name"]}')
        if recipe.get('noncommercial'):
            details.append(text['license_note'])
        if recipe.get('license_url'):
            details.append(recipe['license_url'])
        details.extend(('', text['space'].format(size=_size(required_space))))
        confirmed = console.choose(text['review'], [text['start'], text['back']], details)
        if confirmed != 0:
            continue
        while True:
            console.show(text['preparing'], [text['cancel']])
            try:
                result = install(profile_id, recipe_id, console.progress)
            except Exception as error:
                retry = console.choose(text['failed'], [text['retry'], text['back']], [str(error)])
                if retry == 0:
                    continue
                break
            console.show(text['success'] if recipe_id else text['only_success'])
            return result


def run_setup(profiles: dict, recipes: dict, install, *, data_directory: str,
              language: str | None = None) -> dict | None:
    """Ask for local/external setup; the caller owns installation and persistence.

    Catalog entries are plain dictionaries with name/size; recipes may additionally
    provide license_name, license_url and noncommercial. ``install`` receives the
    selected IDs and a synchronous progress callback. Esc cancels at progress
    boundaries by raising KeyboardInterrupt, leaving resumable files to installer.
    """
    selected_language = language or system_language()
    text = _TEXT['zh-CN' if selected_language == 'zh-CN' else 'en']
    with _console_mode() as interactive:
        console = _Console(text, interactive)
        try:
            return _run(console, profiles, recipes, install, data_directory)
        except (EOFError, KeyboardInterrupt):
            console.show(text['cancelled'])
            return None
