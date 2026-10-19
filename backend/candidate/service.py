"""PMI candidates and reproducible budgeted sequences."""
import hashlib
import json
import math
import random
import secrets
import threading
from collections import OrderedDict
from collections.abc import Sequence

from .errors import CandidateError
from .expansion import PreparedGeneration
from .rounds import integer, validate_options, prepare_rounds

DEFAULT_DOCUMENT = dict(base_positive=[], base_negative=[], min_tags=10, max_tags=30,
                        pmi_threshold=0, min_cooccurrence=10, change_budget=2, blocked_keywords=[])


def document_key(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def keyword_text(text):
    return " ".join(text.replace("_", " ").casefold().split())


def matches_blocked_keyword(name, keywords):
    text = keyword_text(name)
    return any(keyword in text for keyword in keywords)


def validate_document(document):
    if not isinstance(document, dict):
        raise CandidateError("document 必须是对象")
    result = {**DEFAULT_DOCUMENT, **document}
    for key in ("base_positive", "base_negative"):
        values = result[key]
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise CandidateError(f"{key} 必须是完整且非空的标签文本列表")
        result[key] = list(dict.fromkeys(v.strip().replace("_", " ") for v in values))
    keywords = result["blocked_keywords"]
    if not isinstance(keywords, list) or any(not isinstance(value, str) for value in keywords):
        raise CandidateError("blocked_keywords 必须是字符串列表")
    result["blocked_keywords"] = list(dict.fromkeys(
        keyword_text(value) for value in keywords if keyword_text(value)))
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
    def __init__(self, store, libraries=None):
        self.store = store
        self.libraries = libraries
        self.library_stamp = libraries.stamp(store.library_path) if libraries else None
        self._sequence_cache = OrderedDict()
        self._sequence_lock = threading.RLock()
        if not self.store.list_presets():
            self.store.save_preset("default", "默认", self._with_library_floor(
                {**DEFAULT_DOCUMENT, "base_positive": ["general"]}))
        from .provider import CooccurrenceCandidateProvider
        self.provider = CooccurrenceCandidateProvider(self)

    def list_libraries(self):
        return self.libraries.listing()

    def add_library(self, path, filename):
        return self.libraries.add(path, filename)

    def select_library(self, filename):
        if not isinstance(filename, str):
            raise CandidateError("请选择词库文件。")
        path = self.libraries.refresh_path(filename)
        return CandidateService(self.store.with_library(path), self.libraries)

    def list_tags(self, query="", page=1, page_size=15):
        integer(page, "page", 1, 2**31-1)
        integer(page_size, "page_size", 1, 200)
        return self.store.list_tags(query.strip(), page, page_size)

    def resolve_tag_pool(self, positive_prompts: Sequence[str]) -> tuple[str, ...]:
        names = {text.strip().replace(" ", "_")
                 for prompt in positive_prompts for text in prompt.split(",") if text.strip()}
        return tuple(sorted(tag["name"] for tag in self.store.find_tags(names)))

    def list_presets(self):
        return {"presets": self.store.list_presets()}

    def load_preset(self, preset_id):
        try:
            return self.store.load_preset(preset_id)
        except KeyError:
            raise CandidateError(f"未找到预设：{preset_id}") from None

    def normalize_roam_anchors(self, preset_id, pinned_positive):
        document = self.load_preset(preset_id)["document"] if preset_id else DEFAULT_DOCUMENT
        if not isinstance(pinned_positive, list) or any(
                not isinstance(text, str) or not text.strip() for text in pinned_positive):
            raise CandidateError("pinned_positive 必须是完整且非空的提示词列表")
        base, _ = self._fixed(document["base_positive"], "positive", "")
        pins, _ = self._fixed([text.strip().replace("_", " ") for text in pinned_positive], "positive", "")
        base_ids = {term["id"] for term in base}
        return dict(preset_base_positive=[term["text"] for term in base],
                    pinned_positive=[term["text"] for term in pins if term["id"] not in base_ids])

    def _with_library_floor(self, document):
        return {**document, "min_cooccurrence": max(document["min_cooccurrence"],
                                                   self.dataset_status()["min_cooccurrence"])}

    def save_preset(self, payload):
        name = payload.get("name", "").strip()
        if not name:
            raise CandidateError("请填写预设名称 name")
        document = self._with_library_floor(validate_document(payload["document"]))
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

    def _reference_variable(self, document, reference, fixed, anchors, allowed_ids):
        """Resolve the actual prior positive combination against today's preset and vocabulary."""
        texts = [term["text"].strip().replace("_", " ") for term in reference["terms"]
                 if term["channel"] == "positive"]
        if ", ".join(texts) != reference["positive"].strip().replace("_", " "):
            return None  # An edited text is not represented by its historical snapshot.
        fixed_texts = {term["text"] for term in fixed}
        fixed_ids = {term["id"] for term in fixed}
        names = list(dict.fromkeys(text.replace(" ", "_") for text in texts if text not in fixed_texts))
        resolved = {tag["name"]: tag for tag in self.store.find_tags(names)}
        if len(resolved) != len(names):
            return None
        variable = [resolved[name] for name in names if str(resolved[name]["id"]) not in fixed_ids]
        if len(fixed) + len(variable) > document["max_tags"]:
            return None
        if allowed_ids is not None and any(tag["id"] not in allowed_ids for tag in variable):
            return None
        excluded_negative = {keyword_text(text) for text in document["base_negative"]}
        if any(keyword_text(tag["name"]) in excluded_negative or
               matches_blocked_keyword(tag["name"], document["blocked_keywords"]) for tag in variable):
            return None
        existing = list(anchors)
        for tag in variable:
            pairs = self.store.pair_relations(tag["id"], [other["id"] for other in existing])
            if any(other["id"] not in pairs or
                   pairs[other["id"]]["pmi"] < document["pmi_threshold"] or
                   pairs[other["id"]]["count"] < document["min_cooccurrence"] for other in existing):
                return None
            existing.append(tag)
        return variable

    def _extend(self, document, fixed_count, anchors, variable, rng, cap, work, allowed_ids=None, prepared=None):
        variable = list(variable)
        excluded_negative = {keyword_text(term["text"]) for term in prepared.negative}
        reason = "target_length"
        state = None
        while fixed_count + len(variable) < cap:
            if work[0] <= 0:
                return variable, "search_limit"
            work[0] -= 1
            if state is None:
                state = prepared.expansion()
                for tag in variable:
                    state.add(tag)
            choices = state.choices()
            if excluded_negative or document["blocked_keywords"]:
                choices = [(tag, weight) for tag, weight in choices
                           if keyword_text(tag["name"]) not in excluded_negative and
                           not matches_blocked_keyword(tag["name"], document["blocked_keywords"])]
            if not choices:
                return variable, "no_eligible_tags"
            chosen = rng.choices([item[0] for item in choices], [item[1] for item in choices], k=1)[0]
            variable.append(chosen)
            if fixed_count + len(variable) < cap and work[0] > 0:
                state.add(chosen)
        return variable, reason

    def _initial(self, document, fixed_count, anchors, rng, limit, allowed_ids=None, prepared=None):
        target = rng.randint(max(document["min_tags"], fixed_count), document["max_tags"])
        return self._extend(document, fixed_count, anchors, [], rng, target, [limit], allowed_ids, prepared)

    def _advance(self, document, fixed_count, anchors, previous, rng, limit, allowed_ids=None, prepared=None):
        budget = document["change_budget"]
        if not budget:
            return list(previous), "budget_zero", 0
        current = fixed_count + len(previous)
        upper = min(document["max_tags"], current + budget)
        # A partial prior frame can be below min_tags; progress within its budget.
        lower = min(upper, max(document["min_tags"], fixed_count, current - budget))
        target = rng.randint(lower, upper)
        wanted = target - fixed_count
        minimum_removed = max(0, len(previous) - wanted)
        maximum_removed = min(len(previous), (budget + len(previous) - wanted) // 2)
        if target == current:
            if not maximum_removed:
                return list(previous), "target_length", 0
            minimum_removed = 1  # Same length can still replace a tag within the budget.
        previous_ids = {tag["id"] for tag in previous}
        removed = rng.randint(minimum_removed, maximum_removed)
        remove_ids = set(rng.sample([tag["id"] for tag in previous], removed))
        retained = [tag for tag in previous if tag["id"] not in remove_ids]
        tags, reason = self._extend(document, fixed_count, anchors, retained, rng, target, [limit], allowed_ids, prepared)
        changes = len(previous_ids ^ {tag["id"] for tag in tags})
        return tags, reason, changes

    def _sequence(self, document, fixed_count, anchors, seed, step, limit, source_id, allowed_ids=None, prepared=None):
        """Cache only the latest frame; earlier frames and restarts replay deterministically."""
        key = document_key([document, seed, limit, source_id,
                            sorted(allowed_ids) if allowed_ids is not None else None])
        with self._sequence_lock:
            cached = self._sequence_cache.get(key)
            if cached and cached[0] <= step:
                first, variable, reason, changes = cached
            else:
                variable, reason = self._initial(document, fixed_count, anchors, random.Random(seed), limit, allowed_ids, prepared)
                first, changes = 0, 0
            for frame in range(first+1, step+1):
                frame_hash = document_key(["cooccurrence-sequence-v1", seed, frame])
                variable, reason, changes = self._advance(document, fixed_count, anchors, variable,
                                                          random.Random(int(frame_hash, 16)), limit, allowed_ids, prepared)
            self._sequence_cache[key] = (step, variable, reason, changes)
            self._sequence_cache.move_to_end(key)
            while len(self._sequence_cache) > 8:
                self._sequence_cache.popitem(last=False)
            return variable, reason, changes

    def _prepare_generation(self, payload, allowed_positive_tag_ids=None, previous_candidate=None):
        options = validate_options(payload)
        document = validate_document(options.get("document") if "document" in options else
                                     self.load_preset(options["preset_id"])["document"])
        dataset = self.dataset_status()
        if dataset["status"] != "ready":
            raise CandidateError("共现数据尚未导入完成，请等待 dataset 状态为 ready 后再生成")
        document["min_cooccurrence"] = max(document["min_cooccurrence"], dataset["min_cooccurrence"])
        source_id = "danbooru:pmi-v2:general+ratings:min100:pair10:" + (dataset.get("revision") or dataset.get("source") or "local")
        fixed, anchors = self._fixed(document["base_positive"], "positive", source_id)
        negative, _ = self._fixed(document["base_negative"], "negative", source_id)
        previous = (self._reference_variable(document, previous_candidate, fixed, anchors, allowed_positive_tag_ids)
                    if previous_candidate is not None else None)
        return PreparedGeneration(self.store, document, source_id, fixed, anchors, negative,
                                  allowed_positive_tag_ids, previous)

    def generate(self, payload, *, allowed_positive_tag_ids=None, previous_candidate=None):
        prepared = self._prepare_generation(payload, allowed_positive_tag_ids, previous_candidate)
        return self._generate_prepared(prepared, payload)

    def _generate_prepared(self, prepared, payload):
        options = validate_options(payload)
        document, source_id = prepared.document, prepared.source_id
        fixed, anchors, negative = prepared.fixed, prepared.anchors, prepared.negative
        allowed_ids, previous = prepared.allowed_ids, prepared.previous
        seed = secrets.randbits(53) if options["mode"] == "random_each_run" else options["seed"]
        limit = options.get("max_steps", 100)
        step = options["sequence_step"] if options["mode"] == "sequence" else 0
        if previous is not None:
            variable, reason, changes = self._advance(document, len(fixed), anchors, previous,
                                                      random.Random(seed), limit, allowed_ids, prepared)
        elif options["mode"] == "sequence":
            variable, reason, changes = self._sequence(document, len(fixed), anchors, seed, step, limit, source_id, allowed_ids, prepared)
        else:
            variable, reason = self._initial(document, len(fixed), anchors, random.Random(seed), limit, allowed_ids, prepared)
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
