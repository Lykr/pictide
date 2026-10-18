"""Keep application data, runtime files and caches under one chosen directory."""
from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, init=False)
class DataPaths:
    root: Path

    def __init__(self, data_dir=None):
        default = Path(sys.executable).resolve().parents[2] if getattr(sys, "frozen", False) else ROOT / "data"
        selected = data_dir if data_dir is not None else os.environ.get("PICTIDE_DATA_DIR") or os.environ.get("PICTIDE_WEB_DATA_DIR") or default
        object.__setattr__(self, "root", Path(selected).expanduser().resolve())

    @property
    def database(self):
        return self.root / "pictide.sqlite3"

    @property
    def candidate_database(self):
        return self.root / "candidate.sqlite3"

    @property
    def libraries(self):
        return self.root / "libraries"

    @property
    def images(self):
        return self.root / "images"

    @property
    def prompts(self):
        return self.root / "prompts"

    @property
    def workflows(self):
        return self.root / "workflows"

    @property
    def cache(self):
        return self.root / "cache"

    @property
    def logs(self):
        return self.root / "logs"

    @property
    def previews(self):
        return self.root / "previews"

    @property
    def tmp(self):
        return self.root / "tmp"

    @property
    def runtime(self):
        return self.root / "runtime"

    def ensure(self):
        for directory in (self.root, self.libraries, self.images, self.prompts, self.workflows, self.cache, self.logs,
                          self.previews, self.tmp, self.runtime,
                          self.cache / "python", self.cache / "pip"):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def configure_runtime(self):
        """Configure this process only; leave proxy and root logging settings alone."""
        self.ensure()
        os.environ["PICTIDE_DATA_DIR"] = str(self.root)
        os.environ["PICTIDE_WEB_DATA_DIR"] = str(self.root)
        os.environ["TMP"] = os.environ["TEMP"] = str(self.tmp)
        tempfile.tempdir = str(self.tmp)
        os.environ["PYTHONPYCACHEPREFIX"] = str(self.cache / "python")
        sys.pycache_prefix = str(self.cache / "python")
        os.environ["PIP_CACHE_DIR"] = str(self.cache / "pip")

        logger = logging.getLogger("backend")
        target = self.logs / "pictide.log"
        owned = [handler for handler in logger.handlers
                 if getattr(handler, "_pictide_runtime_handler", False)]
        if not any(Path(handler.baseFilename) == target for handler in owned):
            handler = RotatingFileHandler(target, maxBytes=1024 * 1024,
                                          backupCount=3, encoding="utf-8")
            handler._pictide_runtime_handler = True
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            for previous in owned:
                logger.removeHandler(previous)
                previous.close()
            logger.addHandler(handler)
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)
        return self


def configure_runtime(data_dir=None):
    return DataPaths(data_dir).configure_runtime()
