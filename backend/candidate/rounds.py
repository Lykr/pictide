"""Seed and sequence controls shared by candidate generation rounds."""
import secrets

from .errors import CandidateError

MAX_SEED = 2**53 - 1
MAX_SEQUENCE_STEP = 1000
CONTROLS = {"fixed", "increment", "decrement", "randomize"}


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise CandidateError(f"{name} 必须是 {low} 到 {high} 之间的整数")
    return value


def validate_options(payload):
    if not isinstance(payload, dict):
        raise CandidateError("candidate 必须是对象")
    mode = payload.get("mode", "random_each_run")
    if mode not in ("random_each_run", "fixed_seed", "sequence"):
        raise CandidateError("mode 必须是 random_each_run、fixed_seed 或 sequence")
    preset_id = payload.get("preset_id")
    if not isinstance(preset_id, str) or not preset_id:
        raise CandidateError("请通过 candidate.preset_id 选择预设")
    result = dict(preset_id=preset_id, mode=mode,
                  seed=integer(payload.get("seed", 0), "seed", 0, MAX_SEED),
                  sequence_step=integer(payload.get("sequence_step", 0), "sequence_step", 0, MAX_SEQUENCE_STEP))
    for key in ("seed_control", "step_control"):
        control = payload.get(key, "fixed")
        if control not in CONTROLS:
            raise CandidateError(f"{key} 必须是 fixed、increment、decrement 或 randomize")
        result[key] = control
    if payload.get("max_steps") is not None:
        result["max_steps"] = integer(payload["max_steps"], "max_steps", 1, 1_000_000)
    if "document" in payload:
        result["document"] = payload["document"]
    return result


def after(value, control, maximum):
    if control == "increment":
        return min(maximum, value + 1)
    if control == "decrement":
        return max(0, value - 1)
    if control == "randomize":
        return secrets.randbelow(maximum + 1)
    return value


def prepare_rounds(service, payload, repetitions):
    options = validate_options(payload)
    integer(repetitions, "repetitions", 1, 10)
    if "document" not in options:
        options["document"] = service.load_preset(options["preset_id"])["document"]
    results = []
    for _ in range(repetitions):
        results.append(service.generate(options))
        if options["mode"] != "random_each_run":
            options["seed"] = after(options["seed"], options["seed_control"], MAX_SEED)
        if options["mode"] == "sequence":
            options["sequence_step"] = after(options["sequence_step"], options["step_control"], MAX_SEQUENCE_STEP)
    return results, {key: options[key] for key in ("seed", "sequence_step")}
