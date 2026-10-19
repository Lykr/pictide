"""Backend configuration and read-only discovery behind the task boundary."""
from ..generation import create_backend, get_backend_types, validate_backend
from ..generation.workflows import checkpoint_models, resolve_backend
from ..domain import BackendError


class BackendConnections:
    def __init__(self, session, backend_factory=create_backend):
        self.session = session
        self.backend_factory = backend_factory

    def backend_types(self):
        return get_backend_types()

    def validate(self, config):
        return validate_backend(config)

    async def resolve_connection(self, config):
        return await resolve_backend(config, self.session, self.backend_factory)

    async def check_connection(self, config):
        resolved = await self.resolve_connection(config)
        return await self.backend_factory(resolved, self.session).check()

    async def models(self, config):
        names = await checkpoint_models(config, self.session, self.backend_factory)
        requested = config.get("default_checkpoint")
        selected = requested if requested in names else names[0] if names else None
        return {"models": names, "selected": selected}

    async def template(self, config):
        if config.get("kind", "comfyui") != "comfyui":
            raise BackendError("云端生图后端使用模型参数，无需 ComfyUI 工作流模板。")
        draft = dict(config, workflow_mode="default")
        resolved = await self.resolve_connection(draft)
        backend = self.backend_factory(resolved, self.session)
        options = {}
        if hasattr(backend, "input_options"):
            try:
                options = await backend.input_options()
            except BackendError:
                pass  # Optional enum discovery must not prevent graph editing.
        return dict(resolved, input_options=options)
