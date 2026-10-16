"""Backend registry. Add adapters here without changing feed business logic."""
from .base import BackendError, GenerationBackend
from .comfyui import ComfyBackend, validate_comfyui

_BACKENDS = {
    "comfyui": {"label": "ComfyUI", "validate": validate_comfyui, "create": ComfyBackend},
}


def get_backend_types() -> list[dict]:
    return [{"kind": kind, "label": adapter["label"]} for kind, adapter in _BACKENDS.items()]


def validate_backend(config: dict) -> dict:
    if not isinstance(config, dict):
        raise BackendError("Backend configuration must be an object")
    kind = config.get("kind", "comfyui")
    if not isinstance(kind, str) or kind not in _BACKENDS:
        raise BackendError("Unsupported generation backend kind")
    return _BACKENDS[kind]["validate"](config)


def create_backend(config, session) -> GenerationBackend:
    validated = validate_backend(config)
    return _BACKENDS[validated["kind"]]["create"](validated, session)


__all__ = ["BackendError", "GenerationBackend", "ComfyBackend", "validate_backend", "create_backend", "get_backend_types"]
