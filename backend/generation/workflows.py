"""Materialize a standalone default txt2img graph before a job is persisted."""
import copy

from . import create_backend, validate_backend
from .base import BackendError


def default_txt2img(checkpoint):
    return {"workflow":{
        "1":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":checkpoint},"_meta":{"title":"模型"}},
        "2":{"class_type":"CLIPTextEncode","inputs":{"text":"","clip":["1",1]},"_meta":{"title":"正向提示词"}},
        "3":{"class_type":"CLIPTextEncode","inputs":{"text":"","clip":["1",1]},"_meta":{"title":"负向提示词"}},
        "4":{"class_type":"EmptyLatentImage","inputs":{"width":1024,"height":1024,"batch_size":1}},
        "5":{"class_type":"KSampler","inputs":{"seed":0,"steps":28,"cfg":5.5,"sampler_name":"dpmpp_2m","scheduler":"karras","denoise":1.0,"model":["1",0],"positive":["2",0],"negative":["3",0],"latent_image":["4",0]}},
        "6":{"class_type":"VAEDecode","inputs":{"samples":["5",0],"vae":["1",2]}},
        "7":{"class_type":"PreviewImage","inputs":{"images":["6",0]}},
    },"bindings":{"positive":{"node_id":"2","input":"text"},"negative":{"node_id":"3","input":"text"},"seed":{"node_id":"5","input":"seed"}},"output_nodes":["7"]}


def uses_default(config):
    mode = config.get("workflow_mode")
    if mode not in (None,"default","custom"):
        raise BackendError("工作流模式必须为 default 或 custom。")
    return mode == "default" or not config.get("workflow")


async def checkpoint_models(config, session, backend_factory=create_backend):
    probe = {**config,**default_txt2img("__model_discovery__")}
    backend = backend_factory(validate_backend(probe),session)
    return await backend.checkpoints()


async def resolve_backend(config, session, backend_factory=create_backend):
    config = copy.deepcopy(config)
    if not uses_default(config):
        cleaned = validate_backend(config)
        cleaned["workflow_mode"] = "custom"
        return cleaned
    if config.get("kind","comfyui") != "comfyui":
        raise BackendError("此后端暂不支持内置文生图，请导入自定义工作流。")
    models = await checkpoint_models(config,session,backend_factory)
    if not models:
        raise BackendError("ComfyUI 没有可用的 checkpoint。请先在后端安装兼容 SD/SDXL 的模型。")
    chosen = config.get("default_checkpoint", "")
    if not isinstance(chosen,str):
        raise BackendError("默认模型名称必须是文本。")
    chosen = chosen or models[0]
    if chosen not in models:
        raise BackendError("所选默认模型在当前 ComfyUI 后端不可用，请重新读取模型列表。")
    cleaned = validate_backend({**config,**default_txt2img(chosen)})
    cleaned.update(workflow_mode="default",default_checkpoint=chosen)
    return cleaned
