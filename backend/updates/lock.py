"""Cross-process serialization for explicit download and installation operations."""
import os
from pathlib import Path


class UpdateLease:
    def __init__(self, data):
        path = Path(data) / 'tmp/updates/operation.lock'
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open('a+b')
        if self.stream.tell() == 0:
            self.stream.write(b'\0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise ValueError('Another update operation is already running') from None

    def close(self):
        if not self.stream.closed:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()
