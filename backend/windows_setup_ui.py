"""Dependency-free first-run console choices and installation progress."""
from contextlib import contextmanager
import os
import logging
from pathlib import Path
import sys
import time

from backend.desktop_text import system_language
from backend.local_generation import capacity_gib, hardware_issues
from backend.windows_hardware import detect_hardware, select_gpu


_TEXT = {
    'en': {
        'title': 'Welcome to Pictide', 'question': 'How would you like to generate images?',
        'external': 'I already have an image generation API',
        'local': 'Set up local ComfyUI for me', 'later': 'Set up later',
        'keys': 'Up / Down: select   Enter: continue   Esc: back',
        'number': 'Choose a number (Enter / 0: back): ',
        'data_location': 'Data location',
        'data_purpose': 'Models, images and preferences will be saved here.',
        'use_directory': 'Use this directory', 'other_directory': 'Specify another directory',
        'directory_prompt': 'Enter the full directory path (Enter: back): ',
        'directory_absolute': 'Enter an absolute directory path.',
        'directory_kept': 'Data in the previous directory stays there; it will not be moved automatically.',
        'gpu': 'Prepare local image generation',
        'detected': 'You are using a {name} graphics card. Pictide can prepare the matching ComfyUI environment for you.',
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
        'download': 'Estimated download',
        'model_download': 'Model download',
        'hardware_required': 'needs {vram} GB VRAM / {ram} GB RAM',
        'hardware_current': 'Detected: {vram} VRAM / {ram} RAM',
        'unknown_memory': 'unknown', 'hardware_blocked': 'hardware requirements not met',
        'hardware_title': 'This computer does not meet the model requirements',
        'requirements_missing': 'This model has no hardware requirements defined and cannot be downloaded.',
        'hardware_environment': 'This model does not support the selected environment.',
        'hardware_gpu_missing': 'No graphics card matching the selected environment could be confirmed.',
        'hardware_vram': 'VRAM: requires {required} GB; detected {actual}.',
        'hardware_ram': 'RAM: requires {required} GB; detected {actual}.',
        'hardware_alternative': 'Choose another model, or skip the model download.',
        'license': 'Model license',
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
        'data_location': '数据保存位置',
        'data_purpose': '模型、图片和偏好都会保存在这里。',
        'use_directory': '使用此目录', 'other_directory': '指定其他目录',
        'directory_prompt': '输入完整目录路径（Enter 返回）：',
        'directory_absolute': '请输入绝对目录路径。',
        'directory_kept': '原目录的数据会保留在原处，不会自动迁移。',
        'gpu': '准备本地生图环境',
        'detected': '检测到你正在使用 {name} 显卡，可以为你准备对应的 ComfyUI 运行环境。',
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
        'review': '准备下载', 'download': '预计下载体积',
        'model_download': '模型下载',
        'hardware_required': '需 {vram} GB 显存 / {ram} GB 内存',
        'hardware_current': '已检测：显存 {vram} / 内存 {ram}',
        'unknown_memory': '未能读取', 'hardware_blocked': '不满足硬件要求',
        'hardware_title': '这台电脑暂不满足模型要求',
        'requirements_missing': '此模型尚未配置硬件要求，暂不能下载。',
        'hardware_environment': '此模型不支持所选运行环境。',
        'hardware_gpu_missing': '未能确认与所选环境匹配的显卡。',
        'hardware_vram': '显存要求：至少 {required} GB；当前：{actual}。',
        'hardware_ram': '内存要求：至少 {required} GB；当前：{actual}。',
        'hardware_alternative': '可以选择其他模型，或暂不下载模型。',
        'license': '模型许可',
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
        self.last_log_progress = 0.0
        self.last_log_phase = None

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
                if not answer or answer in ('0', '\x1b'):
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
        if phase_key != self.last_log_phase or now - self.last_log_progress >= 5 or (total and downloaded >= total):
            logging.getLogger('backend.local_generation').info('Local preparation phase=%s resource=%s received=%s total=%s',
                                                             phase, name, downloaded, total)
            self.last_log_phase, self.last_log_progress = phase_key, now
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


def _memory(value, text):
    capacity = capacity_gib(value)
    return f'{capacity} GB' if capacity is not None else text['unknown_memory']


def _hardware_messages(issues, text):
    lines = []
    for issue in issues:
        key = issue['code']
        if key in {'vram', 'ram'}:
            actual = issue['actual']
            lines.append(text['hardware_' + key].format(required=issue['required'],
                         actual=f'{actual} GB' if actual is not None else text['unknown_memory']))
        else:
            lines.append(text[key if key == 'requirements_missing' else 'hardware_' + key])
    return [*lines, '', text['hardware_alternative']]


def _choose_model(console, recipes, hardware, profile_id):
    text = console.text
    gpu = select_gpu(hardware, profile_id)
    current = text['hardware_current'].format(
        vram=_memory(gpu.get('vram_bytes') if gpu else None, text),
        ram=_memory(hardware.get('ram_bytes'), text))
    identifiers = list(recipes)
    while True:
        options = []
        for index, entry in enumerate(recipes.values()):
            required = entry.get('hardware')
            label = f'{entry["name"]} · {text["model_download"]}: {_size(_catalog_size(entry))}'
            if required:
                label += ' · ' + text['hardware_required'].format(
                    vram=required['min_vram_gib'], ram=required['min_ram_gib'])
            issues = hardware_issues(required, hardware, profile_id)
            if issues:
                label += ' · ' + text['hardware_blocked']
            elif index == 0:
                label += ' · ' + text['recommended']
            options.append(label)
        model = console.choose(text['model'], options + [text['only']], [current])
        if model is None:
            return False, None
        if model == len(identifiers):
            return True, None
        recipe_id = identifiers[model]
        issues = hardware_issues(recipes[recipe_id].get('hardware'), hardware, profile_id)
        if issues:
            console.choose(text['hardware_title'], [text['back']], _hardware_messages(issues, text))
            continue
        return True, recipe_id


def _choose_profile(console, profiles, detected):
    text = console.text
    if detected:
        profile = detected['profile']
        name = profiles[profile]['name']
        choice = console.choose(text['gpu'], [text['use_detected'].format(name=name), text['choose_other']],
                                [text['detected'].format(name=detected['name'])])
        if choice is None:
            return None
        if choice == 0:
            return profile
    details = [text['gpu_help'], text['compatibility']]
    if not detected:
        details.insert(0, text['gpu_unknown'])
    identifiers = list(profiles)
    index = console.choose(text['gpu_manual'], [
        text.get('profile_' + key, entry['name']) for key, entry in profiles.items()], details)
    return identifiers[index] if index is not None else None


def choose_data_directory(current_directory, *, language=None, error=None) -> str | None:
    """Confirm an absolute data path without creating files or saving settings.

    The caller supplies the currently resolved directory and validates/persists the
    returned selection. Esc, EOF and Ctrl+C return ``None``.
    """
    selected_language = language or system_language()
    text = _TEXT['zh-CN' if selected_language == 'zh-CN' else 'en']
    original = directory = Path(current_directory).expanduser().absolute()
    with _console_mode() as interactive:
        console = _Console(text, interactive)
        try:
            while True:
                details = [text['data_purpose'], str(directory)]
                if directory != original:
                    details.append(text['directory_kept'])
                if error:
                    details.append(str(error))
                choice = console.choose(text['data_location'],
                                        [text['use_directory'], text['other_directory']], details)
                if choice is None:
                    return None
                if choice == 0:
                    return str(directory)
                answer = input('  ' + text['directory_prompt']).strip()
                if answer == '\x1b':
                    return None
                if not answer:
                    continue
                if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in ('"', "'"):
                    answer = answer[1:-1]
                candidate = Path(os.path.expandvars(answer)).expanduser()
                if not candidate.is_absolute():
                    error = text['directory_absolute']
                    continue
                directory = candidate.absolute()
                error = None
        except (EOFError, KeyboardInterrupt):
            return None


def _run(console, profiles, recipes, install):
    text = console.text
    hardware = detect_hardware()
    detected = select_gpu(hardware)
    if detected and detected['profile'] not in profiles:
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
        selected, recipe_id = _choose_model(console, recipes, hardware, profile_id)
        if not selected:
            continue
        recipe = recipes.get(recipe_id, {})
        size = _catalog_size(profile) + _catalog_size(recipe)
        required_space = profile.get('required_space', _catalog_size(profile) * 4) + _catalog_size(recipe)
        details = [text.get('profile_' + profile_id, profile['name']) + (' + ' + recipe['name'] if recipe else ''),
                   f'{text["download"]}: {_size(size)}']
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
                logging.getLogger('backend.local_generation').exception('Local preparation failed profile=%s recipe=%s',
                                                                      profile_id, recipe_id or '-')
                retry = console.choose(text['failed'], [text['retry'], text['back']], [str(error)])
                if retry == 0:
                    continue
                break
            console.show(text['success'] if recipe_id else text['only_success'])
            return result


def run_setup(profiles: dict, recipes: dict, install, *, language: str | None = None) -> dict | None:
    """Ask for local/external setup; the caller owns installation and persistence.

    Catalog entries contain name/size; model recipes require hardware requirements
    and may provide license_name, license_url and noncommercial. ``install`` receives the
    selected IDs and a synchronous progress callback. Esc cancels at progress
    boundaries by raising KeyboardInterrupt, leaving resumable files to installer.
    """
    selected_language = language or system_language()
    text = _TEXT['zh-CN' if selected_language == 'zh-CN' else 'en']
    with _console_mode() as interactive:
        console = _Console(text, interactive)
        try:
            return _run(console, profiles, recipes, install)
        except (EOFError, KeyboardInterrupt):
            logging.getLogger('backend.local_generation').info('Local preparation cancelled')
            console.show(text['cancelled'])
            return None
