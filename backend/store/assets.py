"""Own durable images and exact prompt sidecars under the application's data root."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile

from ..domain import BackendError

EXTENSIONS = {"image/png":".png","image/jpeg":".jpg","image/webp":".webp","image/gif":".gif","image/avif":".avif"}


def atomic_write(path, content, temporary_directory):
    descriptor, temporary = tempfile.mkstemp(prefix="asset-",suffix=".part",dir=temporary_directory)
    try:
        with os.fdopen(descriptor,"wb") as stream:
            stream.write(content)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def local_image(paths, relative):
    if not isinstance(relative,str) or not relative:
        return None
    path = (paths.root / relative).resolve()
    if not path.is_relative_to(paths.images.resolve()) or not path.is_file():
        return None
    return path


async def persist_output(paths, content, mime, output, job):
    """Persist already-fetched image bytes and exact prompts without backend I/O."""
    mime = mime.split(";",1)[0].lower()
    extension = EXTENSIONS.get(mime)
    if not extension:
        raise BackendError("生图后端返回了不支持的图片格式。")
    identity = json.dumps([job["id"],str(output["node_id"]),output["index"]],separators=(",",":"))
    name = hashlib.sha256(identity.encode()).hexdigest()
    target = paths.images / (name + extension)
    sidecar = paths.images / (name + ".json")
    prompts = json.dumps({"positive":job["positive"],"negative":job["negative"]},ensure_ascii=False,indent=2).encode("utf-8")
    await asyncio.to_thread(atomic_write,target,content,paths.tmp)
    await asyncio.to_thread(atomic_write,sidecar,prompts,paths.tmp)
    return {**output,"local_path":target.relative_to(paths.root).as_posix(),"content_type":mime}
