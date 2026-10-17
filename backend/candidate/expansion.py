"""Batch-local immutable base data and independent incremental intersections."""
import threading


class PreparedGeneration:
    def __init__(self, store, document, source_id, fixed, anchors, negative, allowed_ids, previous):
        self.store, self.document, self.source_id = store, document, source_id
        self.fixed, self.anchors, self.negative = fixed, anchors, negative
        self.allowed_ids, self.previous = allowed_ids, previous
        self._tags = None
        self._base = None
        self._tags_lock = threading.Lock()
        self._base_lock = threading.Lock()

    def tags(self):
        with self._tags_lock:
            if self._tags is None:
                self._tags = {ident: dict(id=ident, name=name, post_count=count)
                              for ident, name, count in self.store.generation_tags()}
            return self._tags

    def expansion(self):
        with self._base_lock:
            if self._base is None:
                state = ExpansionState(self)
                for anchor in sorted(self.anchors, key=lambda tag: tag["post_count"]):
                    state.add(anchor)
                # Store only immutable contributions, never a state referring back to this batch.
                self._base = (tuple(state.anchors), state.contributions)
            anchors, contributions = self._base
            return ExpansionState(self, list(anchors),
                                  None if contributions is None else dict(contributions))


class ExpansionState:
    def __init__(self, prepared, anchors=None, contributions=None):
        self.prepared = prepared
        self.anchors = [] if anchors is None else anchors
        self.contributions = {} if prepared.allowed_ids is not None and not prepared.allowed_ids else contributions

    def add(self, anchor):
        document = self.prepared.document
        position = next((index for index, old in enumerate(self.anchors)
                         if old["post_count"] > anchor["post_count"]), len(self.anchors))
        if self.contributions is None:
            rows = self.prepared.store.qualified_relations(
                anchor["id"], document["pmi_threshold"], document["min_cooccurrence"])
            allowed = self.prepared.allowed_ids
            self.contributions = {ident: (pmi,) for ident, pmi in rows
                                  if allowed is None or ident in allowed}
        elif self.contributions:
            current = dict(self.prepared.store.qualified_relations(
                anchor["id"], document["pmi_threshold"], document["min_cooccurrence"],
                self.contributions.keys()))
            self.contributions = {ident: values[:position] + (current[ident],) + values[position:]
                                  for ident, values in self.contributions.items() if ident in current}
        self.anchors.insert(position, anchor)
        self.contributions.pop(anchor["id"], None)

    def choices(self):
        if self.contributions is None:
            allowed = self.prepared.allowed_ids
            return [(tag, tag["post_count"]) for tag in self.prepared.tags().values()
                    if allowed is None or tag["id"] in allowed]
        if not self.contributions:
            return []
        totals = {}
        for ident in sorted(self.contributions):
            values = self.contributions[ident]
            total = values[0]
            for value in values[1:]:
                total += value
            totals[ident] = total
        count = len(self.anchors)
        maximum = max(total / count for total in totals.values())
        tags = self.prepared.tags()
        return [(tags[ident], 2.0 ** (total / count - maximum)) for ident, total in totals.items()]
