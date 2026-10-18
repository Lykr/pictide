"""Copy missing immutable seed files into a portable user's data directory."""
import json
from pathlib import Path
import shutil
import tempfile


def initialize_resources(paths, seed_dir):
    paths.ensure()
    seed_dir = Path(seed_dir)
    manifest = json.loads((seed_dir / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        relative = Path(item["path"])
        source = seed_dir / relative
        target = paths.root / relative
        if not target.resolve().is_relative_to(paths.root):
            raise ValueError("Invalid portable resource path")
        if target.exists():
            continue
        if not source.is_file() or source.stat().st_size != item["bytes"]:
            raise RuntimeError("Portable resource is incomplete: " + str(relative))
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=paths.tmp, delete=False) as temporary:
            temp_path = Path(temporary.name)
        try:
            shutil.copyfile(source, temp_path)
            temp_path.replace(target)
        finally:
            temp_path.unlink(missing_ok=True)
