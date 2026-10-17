"""Provide complete cooccurrence combinations without consulting preference policy."""
from concurrent.futures import ThreadPoolExecutor

from .contracts import Candidate, TagSnapshot
from .rounds import integer, MAX_SEED, MAX_SEQUENCE_STEP


class CooccurrenceCandidateProvider:
    def __init__(self, service):
        self.service = service

    def sample(self, context, *, allowed_positive_tag_ids=None, previous_candidate=None):
        return self.service.generate(context, allowed_positive_tag_ids=allowed_positive_tag_ids,
                                     previous_candidate=previous_candidate)

    @staticmethod
    def _terms(terms):
        return tuple(TagSnapshot(term["source_id"], term["id"], term["text"],
                                 tuple(term["categories"]), term["channel"]) for term in terms)

    def generate(self, context, constraints):
        count = integer(constraints.get("count", 1), "count", 1, 100)
        context = dict(context)
        prompt_mode = constraints.get("prompt_mode", "random")
        previous = constraints.get("previous_candidate")
        if prompt_mode == "stay" and previous is not None:
            return (Candidate(previous["candidate_id"], previous["positive"], previous["negative"],
                              terms=self._terms(previous["terms"])),)
        if "document" not in context:
            context["document"] = self.service.load_preset(context["preset_id"])["document"]
        allowed = constraints.get("allowed_positive_tags")
        allowed_ids = None if allowed is None else frozenset(
            tag["id"] for tag in self.service.store.find_tags(allowed))
        frames = []
        for index in range(count):
            frame = dict(context)
            if prompt_mode in ("along", "stay"):
                # Each option advances from the selected combination, never another pool member.
                frame["mode"] = "fixed_seed" if frame.get("mode") == "fixed_seed" else "random_each_run"
            if frame.get("mode") == "sequence":
                frame["sequence_step"] = min(MAX_SEQUENCE_STEP, frame.get("sequence_step", 0)+index)
            elif frame.get("mode") == "fixed_seed":
                frame["seed"] = (frame.get("seed", 0)+index) % (MAX_SEED+1)
            frames.append(frame)

        prepared = self.service._prepare_generation(
            frames[0], allowed_ids, previous if prompt_mode == "along" else None)

        def generate_one(frame):
            result = self.service._generate_prepared(prepared, frame)
            terms = self._terms(result["selected_tags"])
            return Candidate(result["candidate_id"], result["positive"], result["negative"], terms=terms)

        # Sequence replay shares an ordered frame cache; independent roam options do not.
        if count == 1 or frames[0].get("mode") == "sequence":
            return tuple(map(generate_one, frames))
        with ThreadPoolExecutor(max_workers=min(4, count), thread_name_prefix="candidate") as pool:
            # map preserves seed/frame order even when workers finish out of order.
            return tuple(pool.map(generate_one, frames))
