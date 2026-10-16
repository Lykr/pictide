"""Fetch generation results through the backend interface before local storage."""
from ..store.assets import persist_output


async def cache_output(paths, backend, output, job):
    content, mime = await backend.image(output)
    return await persist_output(paths, content, mime, output, job)
