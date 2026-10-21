"""Small update contracts shared by the HTTP and command-line entry points."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Release:
    version: str
    page: str
    compatible: bool
    reason: str
    asset: dict | None = None


@dataclass(frozen=True)
class Installation:
    root: str
    platform: str
    arch: str
    version: str


PROGRAM_FILES = {
    'win32': ('Pictide.exe', '_internal', 'README.txt', 'LICENSE', 'NOTICE', 'licenses'),
    'darwin': ('Pictide.app',),
    'linux': ('start.sh', 'data/runtime/pictide', 'README.txt', 'LICENSE', 'NOTICE', 'licenses'),
}
