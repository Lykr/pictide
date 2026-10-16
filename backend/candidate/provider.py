"""Provide complete cooccurrence combinations without consulting preference policy."""
from .contracts import Candidate, TagSnapshot
from .rounds import integer, MAX_SEED, MAX_SEQUENCE_STEP


class CooccurrenceCandidateProvider:
    def __init__(self, service):
        self.service = service

    def sample(self, context):
        return self.service.generate(context)

    def generate(self, context, constraints):
        count = integer(constraints.get("count", 1), "count", 1, 20)
        context = dict(context)
        if "document" not in context:
            context["document"] = self.service.load_preset(context["preset_id"])["document"]
        candidates = []
        for index in range(count):
            frame = dict(context)
            if frame.get("mode") == "sequence":
                frame["sequence_step"] = min(MAX_SEQUENCE_STEP, frame.get("sequence_step", 0)+index)
            elif frame.get("mode") == "fixed_seed":
                frame["seed"] = (frame.get("seed", 0)+index) % (MAX_SEED+1)
            result = self.sample(frame)
            terms = tuple(TagSnapshot(term["source_id"], term["id"], term["text"],
                                      tuple(term["categories"]), term["channel"])
                          for term in result["selected_tags"])
            candidates.append(Candidate(result["candidate_id"], result["positive"], result["negative"], terms=terms))
        return tuple(candidates)
