"""PMI candidates and reproducible budgeted sequences."""
import hashlib
import json
import math
import random
import secrets
import threading
from collections import OrderedDict

from .errors import CandidateError
from .rounds import integer, validate_options, prepare_rounds

DEFAULT_DOCUMENT = dict(base_positive=[], base_negative=[], min_tags=5, max_tags=20,
                        pmi_threshold=0, min_cooccurrence=10, change_budget=2)


def document_key(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def validate_document(document):
    if not isinstance(document, dict):
        raise CandidateError("document 必须是对象")
    result = {**DEFAULT_DOCUMENT, **document}
    for key in ("base_positive", "base_negative"):
        values = result[key]
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise CandidateError(f"{key} 必须是完整且非空的标签文本列表")
        result[key] = list(dict.fromkeys(v.strip().replace("_", " ") for v in values))
    integer(result["min_tags"], "min_tags", 1, 1000)
    integer(result["max_tags"], "max_tags", result["min_tags"], 1000)
    integer(result["min_cooccurrence"], "min_cooccurrence", 1, 2**53-1)
    integer(result["change_budget"], "change_budget", 0, 2000)
    value = result["pmi_threshold"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CandidateError("pmi_threshold 必须是有限数值")
    if len(result["base_positive"]) > result["max_tags"]:
        raise CandidateError("固定正向标签数量超过 max_tags，请减少固定标签或提高上限")
    return {key: result[key] for key in DEFAULT_DOCUMENT}


class CandidateService:
    def __init__(self, store):
        self.store = store
        self._sequence_cache = OrderedDict()
        self._sequence_lock = threading.RLock()
        if not self.store.list_presets():
            self.store.save_preset("default", "默认", DEFAULT_DOCUMENT)
        from .provider import CooccurrenceCandidateProvider
        self.provider = CooccurrenceCandidateProvider(self)

    def list_tags(self, query="", page=1, page_size=15):
        integer(page, "page", 1, 2**31-1)
        integer(page_size, "page_size", 1, 200)
        return self.store.list_tags(query.strip(), page, page_size)

    def list_presets(self):
        return {"presets": self.store.list_presets()}

    def load_preset(self, preset_id):
        try:
            return self.store.load_preset(preset_id)
        except KeyError:
            raise CandidateError(f"未找到预设：{preset_id}") from None

    def save_preset(self, payload):
        name = payload.get("name", "").strip()
        if not name:
            raise CandidateError("请填写预设名称 name")
        document = validate_document(payload["document"])
        return self.store.save_preset(payload.get("id"), name, document)

    def delete_preset(self, preset_id):
        return self.store.delete_preset(preset_id)

    def relations(self, anchor, terms):
        if not isinstance(anchor, str) or not anchor.strip():
            raise CandidateError("anchor 必须是完整且非空的提示词")
        if not isinstance(terms, list) or any(not isinstance(text, str) or not text.strip() for text in terms):
            raise CandidateError("terms 必须是完整且非空的提示词列表")
        anchor = anchor.strip().replace("_", " ")
        terms = list(dict.fromkeys(text.strip().replace("_", " ") for text in terms))
        terms = [text for text in terms if text != anchor]
        tag = self.store.find_tag(anchor)
        others = [(text, self.store.find_tag(text)) for text in terms]
        pairs = self.store.pair_relations(tag["id"], [other["id"] for _, other in others if other]) if tag else {}
        result = []
        for text, other in others:
            pair = pairs.get(other["id"]) if other else None
            result.append(dict(text=text, known=other is not None,
                               pmi=pair["pmi"] if pair else None,
                               count=pair["count"] if pair else None))
        return dict(anchor=dict(text=anchor, known=tag is not None), relations=result)

    def dataset_status(self):
        return self.store.dataset_status()

    def prepare_rounds(self, payload, repetitions):
        return prepare_rounds(self, payload, repetitions)

    def _fixed(self, values, channel, source_id):
        terms, anchors = [], []
        seen = set()
        for text in values:
            tag = self.store.find_tag(text)
            tag_id = str(tag["id"]) if tag else "text:" + hashlib.sha256(text.encode()).hexdigest()
            if tag_id in seen:
                continue
            seen.add(tag_id)
            terms.append(dict(id=tag_id, text=tag["name"].replace("_", " ") if tag else text,
                              categories=["rating" if tag["name"] in ("general", "sensitive", "questionable", "explicit") else "general"] if tag else [], channel=channel, source_id=source_id))
            if tag:
                anchors.append(tag)
        return terms, anchors

    def _extend(self, document, fixed_count, anchors, variable, rng, cap, work):
        variable = list(variable)
        reason = "target_length"
        while fixed_count + len(variable) < cap:
            if work[0] <= 0:
                return variable, "search_limit"
            work[0] -= 1
            choices = self.store.expansion_candidates([*anchors, *variable], document["pmi_threshold"],
                                                       document["min_cooccurrence"])
            if not choices:
                return variable, "no_eligible_tags"
            chosen = rng.choices([item[0] for item in choices], [item[1] for item in choices], k=1)[0]
            variable.append(chosen)
        return variable, reason

    def _initial(self, document, fixed_count, anchors, rng, limit):
        target = rng.randint(max(document["min_tags"], fixed_count), document["max_tags"])
        work = [limit]
        while work[0] > 0:
            work[0] -= 1
            tags, reason = self._extend(document, fixed_count, anchors, [], rng, target, work)
            if fixed_count + len(tags) == target:
                return tags, reason
            if not tags and reason == "no_eligible_tags":
                raise CandidateError("当前锚点没有满足共现条件的起始候选，无法满足 min_tags，请调整锚点或阈值")
            # Retry the same target; redrawing it would favour shorter combinations.
        raise CandidateError(f"共现条件或搜索上限 max_steps 无法达到随机目标长度 {target}，请调整数量范围、锚点、阈值或搜索上限")

    def _advance(self, document, fixed_count, anchors, previous, rng, limit):
        budget = document["change_budget"]
        if not budget:
            return list(previous), "budget_zero", 0
        current = fixed_count + len(previous)
        lower = max(document["min_tags"], fixed_count, current - budget)
        upper = min(document["max_tags"], current + budget)
        target = rng.randint(lower, upper)
        wanted = target - fixed_count
        minimum_removed = max(0, len(previous) - wanted)
        maximum_removed = min(len(previous), (budget + len(previous) - wanted) // 2)
        if target == current:
            if not maximum_removed:
                return list(previous), "target_length", 0
            minimum_removed = 1  # Same length can still replace a tag within the budget.
        previous_ids = {tag["id"] for tag in previous}
        work = [limit]
        while work[0] > 0:
            work[0] -= 1
            removed = rng.randint(minimum_removed, maximum_removed)
            remove_ids = set(rng.sample([tag["id"] for tag in previous], removed))
            retained = [tag for tag in previous if tag["id"] not in remove_ids]
            tags, reason = self._extend(document, fixed_count, anchors, retained, rng, target, work)
            changes = len(previous_ids ^ {tag["id"] for tag in tags})
            if fixed_count + len(tags) == target and 0 < changes <= budget:
                return tags, reason, changes
        return list(previous), "held_no_legal_change", 0

    def _sequence(self, document, fixed_count, anchors, seed, step, limit, source_id):
        """Cache only the latest frame; earlier frames and restarts replay deterministically."""
        key = document_key([document, seed, limit, source_id])
        with self._sequence_lock:
            cached = self._sequence_cache.get(key)
            if cached and cached[0] <= step:
                first, variable, reason, changes = cached
            else:
                variable, reason = self._initial(document, fixed_count, anchors, random.Random(seed), limit)
                first, changes = 0, 0
            for frame in range(first+1, step+1):
                frame_hash = document_key(["cooccurrence-sequence-v1", seed, frame])
                variable, reason, changes = self._advance(document, fixed_count, anchors, variable,
                                                          random.Random(int(frame_hash, 16)), limit)
            self._sequence_cache[key] = (step, variable, reason, changes)
            self._sequence_cache.move_to_end(key)
            while len(self._sequence_cache) > 8:
                self._sequence_cache.popitem(last=False)
            return variable, reason, changes

    def generate(self, payload):
        options = validate_options(payload)
        document = validate_document(options.get("document") if "document" in options else
                                     self.load_preset(options["preset_id"])["document"])
        dataset = self.dataset_status()
        if dataset["status"] != "ready":
            raise CandidateError("共现数据尚未导入完成，请等待 dataset 状态为 ready 后再生成")
        seed = secrets.randbits(53) if options["mode"] == "random_each_run" else options["seed"]
        source_id = "danbooru:pmi-v2:general+ratings:min100:pair10:" + (dataset.get("revision") or dataset.get("source") or "local")
        fixed, anchors = self._fixed(document["base_positive"], "positive", source_id)
        negative, _ = self._fixed(document["base_negative"], "negative", source_id)
        limit = options.get("max_steps", 100)
        step = options["sequence_step"] if options["mode"] == "sequence" else 0
        if options["mode"] == "sequence":
            variable, reason, changes = self._sequence(document, len(fixed), anchors, seed, step, limit, source_id)
        else:
            variable, reason = self._initial(document, len(fixed), anchors, random.Random(seed), limit)
            changes = 0
        generated = [dict(id=str(tag["id"]), text=tag["name"].replace("_", " "), categories=["rating" if tag["name"] in ("general", "sensitive", "questionable", "explicit") else "general"],
                          channel="positive", source_id=source_id) for tag in variable]
        terms = [*fixed, *generated, *negative]
        positive_text = ", ".join(term["text"] for term in [*fixed, *generated])
        negative_text = ", ".join(term["text"] for term in negative)
        identity = document_key([source_id, options["preset_id"], document, seed, step, positive_text, negative_text])
        result = dict(positive=positive_text, negative=negative_text, seed=seed, selected_tags=terms,
                      candidate_id=identity, source_id=source_id, preset_id=options["preset_id"],
                      mode=options["mode"], report=dict(stop_reason=reason, tag_count=len(fixed)+len(variable),
                          unrecognized_fixed=[term["text"] for term in fixed if term["id"].startswith("text:")]))
        if options["mode"] == "sequence":
            result["sequence"] = dict(seed=seed, step=step, change_budget=document["change_budget"],
                                      changes=changes)
        return result
