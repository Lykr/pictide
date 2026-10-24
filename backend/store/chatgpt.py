"""Protected OAuth records, separate from browser-visible LLM configuration."""
import asyncio
from contextlib import asynccontextmanager
import ctypes
import json
import os
from pathlib import Path
import tempfile


def _windows_protect(raw, decrypt=False):
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError('Unable to protect or read ChatGPT credentials for this Windows user.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class ChatGPTCredentials:
    def __init__(self, root):
        self.root = Path(root) / 'credentials'
        self.path = self.root / ('chatgpt.dpapi' if os.name == 'nt' else 'chatgpt.json')
        self.lock = asyncio.Lock()

    def _acquire(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != 'nt':
            self.root.chmod(0o700)
        stream = open(self.root / 'chatgpt.lock', 'a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if not stream.seek(0, 2):
                    stream.write(b'0')
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX)
            return stream
        except BaseException:
            stream.close()
            raise

    @asynccontextmanager
    async def transaction(self):
        # Hold the file lock through token refresh, including rotating-token writes.
        async with self.lock:
            task = asyncio.create_task(asyncio.to_thread(self._acquire))
            try:
                stream = await asyncio.shield(task)
            except asyncio.CancelledError:
                (await task).close()
                raise
            try:
                yield self.read()
            finally:
                stream.close()

    def read(self):
        if not self.path.exists():
            return {'accounts': {}}
        raw = self.path.read_bytes()
        if os.name == 'nt':
            raw = _windows_protect(raw, decrypt=True)
        return json.loads(raw)

    def write(self, document):
        raw = json.dumps(document).encode()
        if os.name == 'nt':
            raw = _windows_protect(raw)
        fd, temporary = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
