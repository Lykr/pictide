"""Storage contracts and local persistence adapters."""
from .contracts import Storage
from .sqlite import Repository

__all__ = ["Storage", "Repository"]
