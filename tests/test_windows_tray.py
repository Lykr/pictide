"""A small native tray smoke plus the shared-console ownership boundary."""

import ctypes
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from backend import windows_tray as tray_module


@unittest.skipUnless(sys.platform == "win32", "Windows notification area")
class WindowsTrayTests(unittest.TestCase):
    def test_native_registration_actions_and_cleanup(self):
        api = tray_module._WindowsAPI()
        if not api.FindWindow("Shell_TrayWnd", None):
            self.skipTest("No interactive Explorer notification area")
        opened, logs, exited = (threading.Event() for _ in range(3))
        with tempfile.TemporaryDirectory() as temporary:
            icon = Path(temporary) / "tray.ico"
            # A real 16x16 32-bit ICO, generated without another test dependency.
            bitmap = struct.pack("<IiiHHIIiiII", 40, 16, 32, 1, 32, 0, 1024, 0, 0, 0, 0)
            bitmap += b"\x50\x80\xd0\xff" * 256 + b"\x00" * 64
            icon.write_bytes(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 16, 16, 0, 0, 1, 32, len(bitmap), 22) + bitmap)
            tray = tray_module.WindowsTray(
                icon, "Pictide 测试",
                {"open": "打开 Pictide", "logs": "打开日志目录", "exit": "退出 Pictide"},
                opened.set, logs.set, exited.set,
            )
            try:
                self.assertTrue(tray.start())
                self.assertTrue(tray.start())
                self.assertTrue(tray.hwnd)
                user = ctypes.WinDLL('user32', use_last_error=True)
                get_context = tray_module._bind(user, 'GetWindowDpiAwarenessContext', ctypes.c_void_p, ctypes.c_void_p)
                equal_context = tray_module._bind(user, 'AreDpiAwarenessContextsEqual', ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                self.assertTrue(equal_context(get_context(tray.hwnd), ctypes.c_void_p(-4)))
                self.assertTrue(api.PostMessage(tray.hwnd, tray_module.WM_TRAY, 1, tray_module.WM_LBUTTONDBLCLK))
                self.assertTrue(opened.wait(3), "Double-click must reopen the browser")
                self.assertTrue(api.PostMessage(tray.hwnd, tray_module.WM_COMMAND, tray_module.COMMAND_LOGS, 0))
                self.assertTrue(logs.wait(3))
                self.assertTrue(api.PostMessage(tray.hwnd, tray_module.WM_COMMAND, tray_module.COMMAND_EXIT, 0))
                self.assertTrue(exited.wait(3))
                # The host, rather than this callback, owns service shutdown.
                self.assertTrue(tray.hwnd)
            finally:
                tray.stop()
                tray.stop()
            self.assertIsNone(tray.hwnd)
            self.assertFalse(tray._thread.is_alive())
            missing = tray_module.WindowsTray(
                Path(temporary) / "missing.ico", "Pictide", {}, lambda: None, lambda: None, lambda: None,
            )
            with self.assertLogs("backend", level="ERROR"):
                self.assertFalse(missing.start())
            missing.stop()
            self.assertIsNone(missing.hwnd)
            self.assertFalse(missing._thread.is_alive())

    def test_console_hiding_preserves_other_processes(self):
        kernel, user = Mock(), Mock()
        kernel.GetConsoleWindow.return_value = 123
        kernel.OpenProcess.return_value = 456
        def fill_processes(output, capacity):
            for index, pid in enumerate(processes):
                output[index] = pid
            return len(processes)
        kernel.GetConsoleProcessList.side_effect = fill_processes
        def fill_image(handle, flags, output, size):
            output.value = parent_image
            size._obj.value = len(parent_image)
            return True
        kernel.QueryFullProcessImageNameW.side_effect = fill_image
        with patch.object(ctypes, "WinDLL", side_effect=lambda name, **_: kernel if name == "kernel32" else user):
            processes = [os.getpid(), os.getppid(), max(os.getpid(), os.getppid()) + 1]
            self.assertFalse(tray_module.hide_owned_console())
            user.ShowWindow.assert_not_called()
            processes = [os.getpid(), os.getppid()]
            parent_image = "C:/Windows/System32/cmd.exe"
            self.assertFalse(tray_module.hide_owned_console())
            user.ShowWindow.assert_not_called()
            parent_image = sys.executable
            self.assertTrue(tray_module.hide_owned_console())
            user.ShowWindow.assert_called_once_with(123, 0)


if __name__ == "__main__":
    unittest.main()
