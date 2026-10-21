"""Small Windows notification-area adapter using only the standard library."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger("backend")

WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_NULL = 0x0000
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_TRAY = 0x8001  # WM_APP + 1
COMMAND_OPEN = 1001
COMMAND_LOGS = 1002
COMMAND_EXIT = 1003


if sys.platform == "win32":
    from ctypes import wintypes as wt

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t
    )

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
            ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
            ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
            ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
        ]

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
            ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT),
            ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
            ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
            ("szInfo", wt.WCHAR * 256), ("uVersion", wt.UINT),
            ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
            ("guidItem", GUID), ("hBalloonIcon", wt.HICON),
        ]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wt.HWND), ("message", wt.UINT),
            ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
            ("time", wt.DWORD), ("pt", wt.POINT), ("lPrivate", wt.DWORD),
        ]

    def _bind(dll, name, restype, *argtypes):
        function = getattr(dll, name)
        function.restype = restype
        function.argtypes = list(argtypes)
        return function

    class _WindowsAPI:
        def __init__(self):
            user = ctypes.WinDLL("user32", use_last_error=True)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            shell = ctypes.WinDLL("shell32", use_last_error=True)
            self.SetThreadDpiAwarenessContext = _bind(user, "SetThreadDpiAwarenessContext", wt.HANDLE, wt.HANDLE)
            self.GetDpiForWindow = _bind(user, "GetDpiForWindow", wt.UINT, wt.HWND)
            self.GetSystemMetricsForDpi = _bind(user, "GetSystemMetricsForDpi", ctypes.c_int, ctypes.c_int, wt.UINT)
            self.SetWindowPos = _bind(user, "SetWindowPos", wt.BOOL, wt.HWND, wt.HWND,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT)
            self.FindWindow = _bind(user, "FindWindowW", wt.HWND, wt.LPCWSTR, wt.LPCWSTR)
            self.GetModuleHandle = _bind(kernel, "GetModuleHandleW", wt.HMODULE, wt.LPCWSTR)
            self.RegisterClass = _bind(user, "RegisterClassW", wt.ATOM, ctypes.POINTER(WNDCLASSW))
            self.UnregisterClass = _bind(user, "UnregisterClassW", wt.BOOL, wt.LPCWSTR, wt.HINSTANCE)
            self.CreateWindow = _bind(
                user, "CreateWindowExW", wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR,
                wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p,
            )
            self.DestroyWindow = _bind(user, "DestroyWindow", wt.BOOL, wt.HWND)
            self.DefWindowProc = _bind(
                user, "DefWindowProcW", ctypes.c_ssize_t,
                wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
            )
            self.GetMessage = _bind(user, "GetMessageW", wt.BOOL, ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT)
            self.TranslateMessage = _bind(user, "TranslateMessage", wt.BOOL, ctypes.POINTER(MSG))
            self.DispatchMessage = _bind(user, "DispatchMessageW", ctypes.c_ssize_t, ctypes.POINTER(MSG))
            self.PostMessage = _bind(user, "PostMessageW", wt.BOOL, wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
            self.PostQuitMessage = _bind(user, "PostQuitMessage", None, ctypes.c_int)
            self.RegisterWindowMessage = _bind(user, "RegisterWindowMessageW", wt.UINT, wt.LPCWSTR)
            self.LoadImage = _bind(
                user, "LoadImageW", wt.HANDLE, wt.HINSTANCE, wt.LPCWSTR,
                wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT,
            )
            self.DestroyIcon = _bind(user, "DestroyIcon", wt.BOOL, wt.HICON)
            self.GetSystemMetrics = _bind(user, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
            self.NotifyIcon = _bind(shell, "Shell_NotifyIconW", wt.BOOL, wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
            self.CreatePopupMenu = _bind(user, "CreatePopupMenu", wt.HMENU)
            self.AppendMenu = _bind(user, "AppendMenuW", wt.BOOL, wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR)
            self.DestroyMenu = _bind(user, "DestroyMenu", wt.BOOL, wt.HMENU)
            self.GetCursorPos = _bind(user, "GetCursorPos", wt.BOOL, ctypes.POINTER(wt.POINT))
            self.SetForegroundWindow = _bind(user, "SetForegroundWindow", wt.BOOL, wt.HWND)
            self.TrackPopupMenu = _bind(
                user, "TrackPopupMenu", wt.BOOL, wt.HMENU, wt.UINT,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, ctypes.c_void_p,
            )


class WindowsTray:
    """Own a hidden message window on a dedicated, short-lived message thread.

    Callbacks run on the tray thread; the host dispatches service work to its
    event loop. ``start`` reports success only after Shell_NotifyIcon accepts
    the icon. Unsupported/headless systems retain their existing terminal.
    """

    def __init__(
        self, icon_path: Path, tooltip: str, labels: dict[str, str],
        on_open: Callable[[], None], on_logs: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        self._icon_path = Path(icon_path)
        self._tooltip = tooltip
        self._labels = labels
        self._actions = {
            COMMAND_OPEN: on_open, COMMAND_LOGS: on_logs, COMMAND_EXIT: on_exit,
        }
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stop_requested = threading.Event()
        self._registered = False
        self._hwnd: int | None = None
        self._api = None
        self._wndproc = None
        self._icon_data = None

    @property
    def hwnd(self) -> int | None:
        return self._hwnd

    def start(self) -> bool:
        if sys.platform != "win32":
            return False
        if self._thread and self._thread.is_alive():
            self._ready.wait()
            return self._registered
        self._ready.clear()
        self._stop_requested.clear()
        self._thread = threading.Thread(target=self._run, name="pictide-tray", daemon=True)
        self._thread.start()
        self._ready.wait()
        return self._registered

    def stop(self) -> None:
        self._stop_requested.set()
        if self._api and self._hwnd:
            self._api.PostMessage(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join()

    def _invoke(self, command: int) -> None:
        action = self._actions.get(command)
        if action:
            try:
                action()
            except Exception:
                log.exception("Pictide tray action failed")

    def _show_menu(self) -> None:
        api = self._api
        menu = api.CreatePopupMenu()
        if not menu:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            for command, key in ((COMMAND_OPEN, "open"), (COMMAND_LOGS, "logs"), (COMMAND_EXIT, "exit")):
                if not api.AppendMenu(menu, 0, command, self._labels[key]):
                    raise ctypes.WinError(ctypes.get_last_error())
            point = wt.POINT()
            if not api.GetCursorPos(ctypes.byref(point)):
                raise ctypes.WinError(ctypes.get_last_error())
            # The hidden owner follows the menu's monitor so Windows uses that DPI.
            api.SetWindowPos(self._hwnd, None, point.x, point.y, 0, 0, 0x0015)
            api.SetForegroundWindow(self._hwnd)
            # TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON: dispatch once,
            # retaining Windows' normal menu dismissal behavior.
            command = api.TrackPopupMenu(menu, 0x0100 | 0x0080 | 0x0002, point.x, point.y, 0, self._hwnd, None)
            api.PostMessage(self._hwnd, WM_NULL, 0, 0)
            if command:
                self._invoke(command)
        finally:
            api.DestroyMenu(menu)

    def _window_message(self, hwnd, message, wparam, lparam):
        api = self._api
        try:
            if message == WM_CLOSE:
                api.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                if self._registered:
                    api.NotifyIcon(2, ctypes.byref(self._icon_data))
                    self._registered = False
                self._hwnd = None
                api.PostQuitMessage(0)
                return 0
            if message == WM_COMMAND:
                self._invoke(wparam & 0xFFFF)
                return 0
            if message == WM_TRAY:
                if lparam == WM_LBUTTONDBLCLK:
                    self._invoke(COMMAND_OPEN)
                elif lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._show_menu()
                return 0
            if self._taskbar_created and message == self._taskbar_created and self._registered:
                if not api.NotifyIcon(0, ctypes.byref(self._icon_data)):
                    log.warning("Could not restore the Pictide tray icon after Explorer restarted")
                return 0
        except Exception:
            log.exception("Pictide tray window action failed")
        return api.DefWindowProc(hwnd, message, wparam, lparam)

    def _run(self) -> None:
        api = None
        icon = None
        atom = 0
        instance = None
        classname = f"PictideTray_{os.getpid()}_{id(self):x}"
        try:
            self._api = api = _WindowsAPI()
            # PMv2 scales native popup menus instead of bitmap-stretching 96-DPI UI.
            if not api.SetThreadDpiAwarenessContext(-4):
                raise ctypes.WinError(ctypes.get_last_error())
            taskbar = api.FindWindow("Shell_TrayWnd", None)
            if not taskbar:
                log.warning("Windows notification area is unavailable; keeping the terminal open")
                return
            self._taskbar_created = api.RegisterWindowMessage("TaskbarCreated")
            instance = api.GetModuleHandle(None)
            self._wndproc = WNDPROC(self._window_message)
            window_class = WNDCLASSW()
            window_class.lpfnWndProc = self._wndproc
            window_class.hInstance = instance
            window_class.lpszClassName = classname
            atom = api.RegisterClass(ctypes.byref(window_class))
            if not atom:
                raise ctypes.WinError(ctypes.get_last_error())
            self._hwnd = api.CreateWindow(0, classname, "Pictide", 0, 0, 0, 0, 0, None, None, instance, None)
            if not self._hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            # IMAGE_ICON, LR_LOADFROMFILE; the private icon is released below.
            icon = api.LoadImage(
                None, str(self._icon_path.resolve()), 1,
                api.GetSystemMetricsForDpi(49, api.GetDpiForWindow(taskbar)),
                api.GetSystemMetricsForDpi(50, api.GetDpiForWindow(taskbar)), 0x0010,
            )
            if not icon:
                raise ctypes.WinError(ctypes.get_last_error())
            data = self._icon_data = NOTIFYICONDATAW()
            data.cbSize = ctypes.sizeof(data)
            data.hWnd, data.uID = self._hwnd, 1
            data.uFlags = 1 | 2 | 4  # NIF_MESSAGE | NIF_ICON | NIF_TIP
            data.uCallbackMessage, data.hIcon = WM_TRAY, icon
            data.szTip = self._tooltip.encode("utf-16-le")[:254].decode("utf-16-le", errors="ignore")
            if not api.NotifyIcon(0, ctypes.byref(data)):  # NIM_ADD
                raise OSError("Shell_NotifyIcon could not register the Pictide icon")
            self._registered = True
            self._ready.set()
            if self._stop_requested.is_set():
                return
            message = MSG()
            while True:
                result = api.GetMessage(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if result == 0:
                    break
                api.TranslateMessage(ctypes.byref(message))
                api.DispatchMessage(ctypes.byref(message))
        except Exception:
            log.exception("Pictide tray could not start; keeping the terminal open")
        finally:
            if api:
                if self._registered:
                    api.NotifyIcon(2, ctypes.byref(self._icon_data))  # NIM_DELETE
                self._registered = False
                if self._hwnd:
                    api.DestroyWindow(self._hwnd)
                self._hwnd = None
                if icon:
                    api.DestroyIcon(icon)
                if atom:
                    api.UnregisterClass(classname, instance)
            self._wndproc = None
            self._ready.set()


def hide_owned_console() -> bool:
    """Hide only a console shared exclusively by this process/bootloader parent."""
    if sys.platform != "win32":
        return False
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        user = ctypes.WinDLL("user32", use_last_error=True)
        get_console = _bind(kernel, "GetConsoleWindow", wt.HWND)
        get_processes = _bind(kernel, "GetConsoleProcessList", wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD)
        show_window = _bind(user, "ShowWindow", wt.BOOL, wt.HWND, ctypes.c_int)
        hwnd = get_console()
        if not hwnd:
            return False
        processes = (wt.DWORD * 16)()
        count = get_processes(processes, len(processes))
        # A larger shared console necessarily contains unrelated processes.
        if not count or count > len(processes):
            return False
        if not set(processes[:count]).issubset({os.getpid(), os.getppid()}):
            return False
        if os.getppid() in processes[:count]:
            # A user-owned cmd/PowerShell can also be our sole console parent.
            # Only a parent running this same executable is the bootloader.
            open_process = _bind(kernel, "OpenProcess", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
            query_image = _bind(kernel, "QueryFullProcessImageNameW", wt.BOOL, wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD))
            close_handle = _bind(kernel, "CloseHandle", wt.BOOL, wt.HANDLE)
            parent = open_process(0x1000, False, os.getppid())  # PROCESS_QUERY_LIMITED_INFORMATION
            if not parent:
                return False
            try:
                image = ctypes.create_unicode_buffer(32768)
                size = wt.DWORD(len(image))
                if not query_image(parent, 0, image, ctypes.byref(size)):
                    return False
                if os.path.normcase(os.path.realpath(image.value)) != os.path.normcase(os.path.realpath(sys.executable)):
                    return False
            finally:
                close_handle(parent)
        show_window(hwnd, 0)  # SW_HIDE; return value describes previous visibility.
        return True
    except Exception:
        log.exception("Could not hide Pictide's startup console")
        return False
