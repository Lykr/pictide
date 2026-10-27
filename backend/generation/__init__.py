"""Backend registry. Add adapters here without changing feed business logic."""
import re

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
    prompt_type = config.get("prompt_type", "danbooru")
    if prompt_type not in ("danbooru", "natural_language"):
        raise BackendError("Prompt type must be danbooru or natural_language")
    llm_id = config.get('llm_id', 'legacy-prompt-api')
    if not isinstance(llm_id, str) or len(llm_id) > 80:
        raise BackendError('Invalid LLM API selection')
    result = dict(_BACKENDS[kind]["validate"](config), prompt_type=prompt_type, llm_id=llm_id)
    if 'canvas_pool_id' in config:
        identifier = config['canvas_pool_id']
        if not isinstance(identifier, str) or identifier and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifier):
            raise BackendError('Invalid canvas pool selection.')
        result['canvas_pool_id'] = identifier
        if identifier and not backend_capabilities(result)['dimensions']:
            raise BackendError('This API needs width and height inputs to use a pixel-size pool.')
    return result


def create_backend(config, session) -> GenerationBackend:
    validated = validate_backend(config)
    return _BACKENDS[validated["kind"]]["create"](validated, session)


def backend_capabilities(config) -> dict:
    cloud = config.get("kind", "comfyui") != "comfyui"
    bindings = config.get("bindings", {})
    return {"cloud": cloud, "negative_prompt": not cloud and "negative" in bindings,
            "seed": not cloud and "seed" in bindings, "models": not cloud,
            "dimensions": config.get("kind", "comfyui") == "openai" or (not cloud and all(key in bindings for key in ("width", "height"))),
            "events": not cloud, "cancel": not cloud, "recovery": not cloud}


def available_canvas_sizes(config, sizes):
    if not backend_capabilities(config)['dimensions']:
        return []
    if config.get('kind', 'comfyui') == 'comfyui':
        return [size for size in sizes if all(size[key] % 8 == 0 for key in ('width', 'height'))]
    return list(sizes)


__all__ = ["BackendError", "GenerationBackend", "CompletedGeneration", "ComfyBackend", "validate_backend", "create_backend", "get_backend_types", "backend_capabilities", "available_canvas_sizes"]
