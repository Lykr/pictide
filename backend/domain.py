"""Shared value validation and errors; no transport or persistence imports."""
import secrets

class ValidationError(ValueError):
    pass

class ConflictError(ValidationError):
    pass

class NotFoundError(LookupError):
    pass

class GoneError(LookupError):
    pass

class BackendError(Exception):
    def __init__(self, message: str, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


def roam_can_enqueue(state, target):
    """Keep one prepared roam job ahead of the currently executing job."""
    return (not state["paused"] and state["ready"] + state["roam_pending"] < target
            and state["roam_pending"] < 2 and state["pending"] < 10)


def feedback_value(value):
    if value is not None and (type(value) is not int or value != 1):
        raise ValidationError("喜欢状态必须是 1 或 null。")
    return value

def generation_fields(payload: dict) -> dict:
    positive = payload.get("positive")
    negative = payload.get("negative", "")
    if not isinstance(positive, str) or not positive.strip():
        raise ValidationError("请输入正向提示词。")
    if not isinstance(negative, str):
        raise ValidationError("负向提示词必须是文本。")
    if len(positive) > 20000 or len(negative) > 20000:
        raise ValidationError("单条提示词最多 20000 个字符。")
    seed = payload.get("seed", -1)
    if type(seed) is not int or not -1 <= seed <= 2**53 - 1:
        raise ValidationError("种子必须是 -1 或 0 至 9007199254740991 的整数。")
    backend_id = payload.get("backend_id")
    request_id = payload.get("request_id")
    if not isinstance(backend_id, str) or not backend_id:
        raise ValidationError("请选择生图后端。")
    if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
        raise ValidationError("需要有效的 request_id。")
    return {"backend_id": backend_id, "request_id": request_id,
            "positive": positive, "negative": negative, "seed": seed}


def actual_seed(seed: int) -> int:
    return secrets.randbits(53) if seed == -1 else seed


def generation_count(value=1) -> int:
    if type(value) is not int or not 1 <= value <= 10:
        raise ValidationError("生成数量必须是 1 至 10 的整数。")
    return value
