"""Small system-language text catalog for startup and desktop integration."""
import ctypes
import locale
import os
import sys


def _windows_ui_language():
    """Read the user's display language rather than their regional format."""
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetUserDefaultUILanguage.restype = ctypes.c_ushort
    return kernel32.GetUserDefaultUILanguage()


def system_language():
    """Use Simplified Chinese where explicitly requested, English otherwise."""
    try:
        desktop_language = os.environ.get('PICTIDE_DESKTOP_LANGUAGE')
        if sys.platform == 'darwin' and desktop_language in ('zh-CN', 'en'):
            return desktop_language
        if sys.platform == 'win32':
            # Chinese (Simplified), Chinese (PRC), and Chinese (Singapore).
            return 'zh-CN' if _windows_ui_language() in (0x0004, 0x0804, 0x1004) else 'en'
        language = next((os.environ[name] for name in ('LC_ALL', 'LC_MESSAGES', 'LANG')
                         if os.environ.get(name)), None)
        language = language or locale.getlocale()[0] or ''
        language = language.split('.')[0].split('@')[0].replace('_', '-').lower()
        simplified = (language in ('zh-cn', 'zh-sg', 'zh-hans')
                      or language.startswith('zh-hans-'))
        return 'zh-CN' if simplified else 'en'
    except (AttributeError, OSError, ValueError):
        return 'en'


_TEXT = {
    'en': {
        'vocabulary_choose': 'No valid vocabulary found. Choose an edition to download:',
        'vocabulary_filtered': 'filtered (recommended): excludes questionable and explicit source ratings.',
        'vocabulary_all_ratings': 'all-ratings: includes all source ratings; may generate explicit content.',
        'terminal_keys': 'Up / Down: select   Enter: confirm   Esc: back',
        'terminal_text_keys': 'Type a path · Enter: confirm · Esc: back',
        'terminal_error': 'Could not continue',
        'vocabulary_explicit_warning': 'Warning: all-ratings includes explicit source material and may generate explicit content.',
        'vocabulary_downloading': 'Downloading vocabulary: {edition}',
        'vocabulary_progress': 'Vocabulary {edition}: {percent}% ({received:,}/{total:,} bytes)',
        'vocabulary_retry': 'Vocabulary download retry {attempt}/2: {edition} ({error})',
        'vocabulary_ready': 'Vocabulary ready: {filename}',
        'vocabulary_failed': 'Cannot prepare vocabulary {edition}: {error}. Check the connection and restart to resume the download.',
        'preparing_model': 'Preparing MiniLM before starting Pictide: {directory}',
        'downloading_model': 'Downloading MiniLM: {path}',
        'model_progress': 'MiniLM {path}: {percent}% ({received:,}/{total:,} bytes)',
        'model_verified': 'MiniLM verified: {path}',
        'model_retry': 'MiniLM download retry {attempt}/2: {path} ({error})',
        'model_ready': 'MiniLM ready. Starting Pictide.',
        'model_failed': ('Cannot prepare MiniLM {path}: {error}. '
                         'Check the connection and restart to resume the download.'),
        'model_preserved': 'Previous model file preserved: {path}',
        'invalid_model_path': 'Model files must remain inside the selected model directory',
        'starting': 'Starting Pictide…',
        'updating': 'Updating Pictide…',
        'comfy_starting': 'Starting ComfyUI…',
        'startup_log': 'Startup log: {path}',
        'comfy_waiting': '{elapsed} · Waiting for ComfyUI',
        'comfy_ready': 'ComfyUI is ready · {elapsed}',
        'comfy_failed': 'ComfyUI startup failed · {elapsed}',
        'comfy_cancelled': 'ComfyUI startup cancelled · {elapsed}',
        'ready': 'Pictide is running.',
        'local_address': 'Local: {address}',
        'lan_address': 'LAN: {address}',
        'data_directory': 'Data: {directory}',
        'startup_failed': 'Pictide could not start: {error}',
        'tray_unavailable': 'System tray unavailable. Keep this window open while using Pictide.',
        'stopping': 'Stopping Pictide…',
        'open': 'Open Pictide',
        'logs': 'View logs',
        'exit': 'Exit Pictide',
        'already_running': 'Pictide is already running. Opening the web interface.',
        'instance_starting': 'Pictide is already starting. Please wait.',
    },
    'zh-CN': {
        'vocabulary_choose': '未检测到有效词库，请选择要下载的版本：',
        'vocabulary_filtered': 'filtered（推荐）：排除 questionable 和 explicit 分级来源。',
        'vocabulary_all_ratings': 'all-ratings：包含全部分级来源，可能生成露骨内容。',
        'terminal_keys': '↑ ↓ 选择 · Enter 确认 · Esc 返回',
        'terminal_text_keys': '输入路径 · Enter 确认 · Esc 返回',
        'terminal_error': '暂时无法继续',
        'vocabulary_explicit_warning': '注意：all-ratings 包含露骨内容来源，可能生成露骨内容。',
        'vocabulary_downloading': '正在下载词库：{edition}',
        'vocabulary_progress': '词库 {edition}：{percent}%（{received:,}/{total:,} 字节）',
        'vocabulary_retry': '词库下载重试 {attempt}/2：{edition}（{error}）',
        'vocabulary_ready': '词库已就绪：{filename}',
        'vocabulary_failed': '无法准备词库 {edition}：{error}。请检查网络后重新启动，将继续下载。',
        'preparing_model': '正在准备 MiniLM，完成后启动 Pictide：{directory}',
        'downloading_model': '正在下载 MiniLM：{path}',
        'model_progress': 'MiniLM {path}：{percent}%（{received:,}/{total:,} 字节）',
        'model_verified': 'MiniLM 校验完成：{path}',
        'model_retry': 'MiniLM 下载重试 {attempt}/2：{path}（{error}）',
        'model_ready': 'MiniLM 已就绪，正在启动 Pictide。',
        'model_failed': '无法准备 MiniLM {path}：{error}。请检查网络连接，重新启动后会继续下载。',
        'model_preserved': '已保留原模型文件：{path}',
        'invalid_model_path': '模型文件必须位于所选模型目录内',
        'starting': '正在启动 Pictide…',
        'updating': '正在更新 Pictide…',
        'comfy_starting': '正在启动 ComfyUI…',
        'startup_log': '启动日志：{path}',
        'comfy_waiting': '{elapsed} · 正在等待 ComfyUI 就绪',
        'comfy_ready': 'ComfyUI 已就绪 · 用时 {elapsed}',
        'comfy_failed': 'ComfyUI 启动失败 · 已等待 {elapsed}',
        'comfy_cancelled': '已取消 ComfyUI 启动 · 已等待 {elapsed}',
        'ready': 'Pictide 正在运行。',
        'local_address': '本机访问：{address}',
        'lan_address': '局域网访问：{address}',
        'data_directory': '数据目录：{directory}',
        'startup_failed': 'Pictide 启动失败：{error}',
        'tray_unavailable': '系统托盘不可用，使用 Pictide 时请保持此窗口开启。',
        'stopping': '正在退出 Pictide…',
        'open': '打开 Pictide',
        'logs': '查看日志',
        'exit': '退出 Pictide',
        'already_running': 'Pictide 已在运行，正在打开网页。',
        'instance_starting': 'Pictide 正在启动，请稍候。',
    },
}


def translate(key, **kwargs):
    return _TEXT[system_language()][key].format(**kwargs)
