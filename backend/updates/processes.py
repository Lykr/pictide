"""Find processes executing this installation before replacing its program files."""
import ctypes
import os
from pathlib import Path
import sys


def running_pids(installation):
    root = Path(installation.root)
    if installation.platform == 'darwin':
        entries = [root / 'Pictide.app/Contents/MacOS/Pictide', root / 'Pictide.app/Contents/MacOS/PictideService']
    else:
        entries = [root / ('Pictide.exe' if installation.platform == 'win32' else 'data/runtime/pictide/Pictide')]
    names = {str(path.resolve()).casefold() for path in entries}
    result = set()
    if sys.platform == 'win32':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
        ids = (ctypes.c_ulong * 32768)()
        used = ctypes.c_ulong()
        if not ctypes.WinDLL('psapi').EnumProcesses(ids, ctypes.sizeof(ids), ctypes.byref(used)):
            raise ctypes.WinError()
        for pid in ids[:used.value // ctypes.sizeof(ctypes.c_ulong)]:
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                continue
            try:
                buffer = ctypes.create_unicode_buffer(32768)
                length = ctypes.c_ulong(len(buffer))
                if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)) and str(Path(buffer.value).resolve()).casefold() in names:
                    result.add(pid)
            finally:
                kernel.CloseHandle(handle)
    elif sys.platform == 'darwin':
        import subprocess
        library = ctypes.CDLL('/usr/lib/libproc.dylib')
        library.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        pids = subprocess.check_output(['/bin/ps', '-axo', 'pid='], text=True).split()
        for value in pids:
            buffer = ctypes.create_string_buffer(4096)
            if library.proc_pidpath(int(value), buffer, len(buffer)) > 0 and str(Path(os.fsdecode(buffer.value)).resolve()).casefold() in names:
                result.add(int(value))
    else:
        for path in Path('/proc').glob('[0-9]*/exe'):
            try:
                if str(path.resolve(strict=True)).casefold() in names:
                    result.add(int(path.parent.name))
            except (OSError, RuntimeError):
                pass
    return result
