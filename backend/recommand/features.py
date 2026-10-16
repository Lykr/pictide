"""Content identity and split-channel features; no vocabulary dependencies."""
import hashlib
import json
import math
import unicodedata
from collections import Counter

from ..contracts.recommendation import ScoreCandidate, ScoreTerm

SEMANTIC_DIMENSION = 768
FEATURE_RECIPE = "nfc-strip-v1;exact-channel-l2;mean-channel-l2;semantic-weight=.25;dim=384"


def normalize_text(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Term text must be a non-empty string")
    return unicodedata.normalize("NFC", text.strip())


def content_key(text, channel):
    if channel not in ("positive", "negative"):
        raise ValueError("Term channel must be positive or negative")
    return json.dumps([channel, normalize_text(text)], ensure_ascii=False, separators=(",", ":"))


def feature_version(model_version):
    digest = hashlib.sha256((model_version + ":" + FEATURE_RECIPE).encode("utf-8")).hexdigest()
    return "combination-v1:" + digest


def joined_text(parts):
    # Mirror the public text format without depending on candidate implementation.
    return ", ".join(text.strip().strip(",").strip() for text in parts
                     if text.strip().strip(",").strip())


def validate_candidate(candidate):
    if not isinstance(candidate, ScoreCandidate) or not isinstance(candidate.candidate_id, str) or not candidate.candidate_id:
        raise ValueError("Each candidate requires a non-empty candidate_id")
    if not isinstance(candidate.terms, (tuple, list)) or not all(isinstance(term, ScoreTerm) for term in candidate.terms):
        raise ValueError("Candidate terms must be ordered ScoreTerm snapshots")
    for channel in ("positive", "negative"):
        full = getattr(candidate, channel)
        if not isinstance(full, str):
            raise ValueError("Complete prompt text must be a string")
        texts = []
        for term in candidate.terms:
            content_key(term.text, term.channel)
            if not term.text.strip().strip(",").strip():
                raise ValueError("Term must contain prompt content")
            if term.channel == channel:
                texts.append(term.text)
        if unicodedata.normalize("NFC", full) != unicodedata.normalize("NFC", joined_text(texts)):
            raise ValueError("Complete prompt text does not match ordered term snapshot")


class FeatureEncoder:
    def __init__(self, store, encoder):
        self.store = store
        self.encoder = encoder

    def prepare(self, candidates):
        import numpy as np
        for candidate in candidates:
            validate_candidate(candidate)
        texts = sorted({normalize_text(term.text) for c in candidates for term in c.terms})
        vectors = self.store.load_vectors(self.encoder.version, texts)
        missing = [text for text in texts if text not in vectors]
        if missing:
            encoded = list(self.encoder.encode(missing))
            if len(encoded) != len(missing):
                raise ValueError("Encoder returned wrong number of vectors")
            fresh = {text: tuple(float(v) for v in vector) for text, vector in zip(missing, encoded)}
            for vector in fresh.values():
                self._validate_vector(vector)
            self.store.save_vectors(self.encoder.version, fresh)
            vectors.update(fresh)
        for text in texts:
            self._validate_vector(vectors[text])
        result = []
        for candidate in candidates:
            semantic = np.zeros(SEMANTIC_DIMENSION, dtype=np.float64)
            exact = {}
            for channel_index, channel in enumerate(("positive", "negative")):
                terms = [term for term in candidate.terms if term.channel == channel]
                if not terms:
                    continue
                counts = Counter(content_key(term.text, channel) for term in terms)
                norm = math.sqrt(sum(value * value for value in counts.values()))
                exact.update({key: value / norm for key, value in counts.items()})
                mean = np.mean([vectors[normalize_text(term.text)] for term in terms], axis=0)
                length = float(np.linalg.norm(mean))
                if length > 0:
                    mean = mean / length
                start = channel_index * 384
                semantic[start:start + 384] = mean * .25
            result.append((semantic, exact))
        return result

    @staticmethod
    def _validate_vector(vector):
        if len(vector) != 384 or not all(math.isfinite(float(v)) for v in vector):
            raise ValueError("Encoder/cache vector must contain 384 finite numbers")


def dense_features(prepared, term_keys):
    import numpy as np
    indices = {key: SEMANTIC_DIMENSION + i for i, key in enumerate(term_keys)}
    result = np.zeros((len(prepared), SEMANTIC_DIMENSION + len(term_keys)), dtype=np.float64)
    for row, (semantic, exact) in enumerate(prepared):
        result[row, :SEMANTIC_DIMENSION] = semantic
        for key, value in exact.items():
            result[row, indices[key]] = value
    return result
