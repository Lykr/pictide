"""Backend registry. Add adapters here without changing feed business logic."""
from .base import BackendError, GenerationBackend, CompletedGeneration
from .comfyui import ComfyBackend, validate_comfyui
from .cloud import OpenAIBackend, GeminiBackend, validate_openai, validate_gemini

_BACKENDS = {
    "comfyui": {"label": "ComfyUI", "validate": validate_comfyui, "create": ComfyBackend},
    "openai": {"label": "OpenAI Images", "validate": validate_openai, "create": OpenAIBackend},
    "gemini": {"label": "Gemini Interactions", "validate": validate_gemini, "create": GeminiBackend},
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


def backend_capabilities(config) -> dict:
    cloud = config.get("kind", "comfyui") != "comfyui"
    bindings = config.get("bindings", {})
    return {"cloud": cloud, "negative_prompt": not cloud and "negative" in bindings,
            "seed": not cloud and "seed" in bindings, "models": not cloud,
            "events": not cloud, "cancel": not cloud, "recovery": not cloud}


__all__ = ["BackendError", "GenerationBackend", "CompletedGeneration", "ComfyBackend", "validate_backend", "create_backend", "get_backend_types", "backend_capabilities"]
