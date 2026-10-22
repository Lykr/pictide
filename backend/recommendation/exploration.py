"""Bounded contrast exploration of existing, complete candidate combinations."""
from collections import Counter, defaultdict
from itertools import combinations

from .features import content_key
from . import policy

EXPLORATION_RATE = .2
BONUS_LIMIT = .2
MAX_TERMS = 32
MAX_PAIRS = 8
MIN_JOINT = 3


def is_exploration_round(seed):
    import numpy as np
    # A separate stream leaves the original Thompson draw unchanged on fallback.
    rng = np.random.default_rng(np.random.SeedSequence([seed, 0x434F4E54]))
    return rng.random() < EXPLORATION_RATE


def occurrences(evidence):
    """Index currently rated images, not feedback events or corpus frequencies."""
    result = defaultdict(set)
    for item in evidence:
        if item.value is None:
            continue
        keys = {content_key(term.text, term.channel) for term in item.candidate.terms
                if term.channel == "positive"}
        for key in keys:
            result[key].add(item.artifact_id)
    return {key: frozenset(images) for key, images in result.items()}


def candidate_pairs(prepared, observed):
    """Bound pair search to learned positive terms that vary in this pool."""
    counts = Counter(key for _, exact in prepared for key in exact if key in observed)
    keys = sorted((key for key, count in counts.items() if count < len(prepared)),
                  key=lambda key: (-len(observed[key]), key))[:MAX_TERMS]
    pairs = []
    for a, b in combinations(range(len(keys)), 2):
        # Presence must differ in at least one complete candidate.
        if not any((keys[a] in exact) != (keys[b] in exact) for _, exact in prepared):
            continue
        left, right = observed[keys[a]], observed[keys[b]]
        joint = len(left & right)
        if joint >= MIN_JOINT:
            pairs.append((a, b, joint / (len(left) + len(right) - joint)))
    return keys, pairs


def rewards(factor, term_keys, prepared, vectors, observed):
    """Return max Q * relative variance reduction per candidate, using full P."""
    import numpy as np
    result = np.zeros(len(prepared), dtype=np.float64)
    keys, pairs = candidate_pairs(prepared, observed)
    if not pairs:
        return result
    offset = len(factor) - len(term_keys)
    indices = {key: offset + index for index, key in enumerate(term_keys)}
    axes = np.zeros((len(factor), len(keys)), dtype=np.float64)
    axes[[indices[key] for key in keys], np.arange(len(keys))] = 1.
    whitened = policy._triangular_solve(factor, axes, True)
    covariance = whitened.T @ whitened
    ranked = []
    for a, b, joint_ratio in pairs:
        total = covariance[a, a] + covariance[b, b]
        plus = total + 2 * covariance[a, b]
        minus = total - 2 * covariance[a, b]
        priority = joint_ratio * np.clip(1 - plus / 2, 0, 1) * np.clip(minus / 2, 0, 1)
        if priority > 1e-12 and minus > 1e-12:
            ranked.append((float(priority), a, b, float(minus)))
    ranked.sort(key=lambda pair: (-pair[0], keys[pair[1]], keys[pair[2]]))
    if not ranked:
        return result
    # Each column contains a full candidate, including semantic/negative axes.
    candidates = policy._triangular_solve(factor, vectors.T, True)
    feedback_variance = 1 + np.sum(candidates * candidates, axis=0)
    for priority, a, b, difference_variance in ranked[:MAX_PAIRS]:
        correlation = (whitened[:, a] - whitened[:, b]) @ candidates
        reduction = correlation ** 2 / feedback_variance
        relative = np.clip(reduction / difference_variance, 0, 1)
        result = np.maximum(result, priority * relative)
    return result
