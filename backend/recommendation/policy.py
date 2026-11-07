"""Full-covariance, signed-evidence Bayesian linear policy."""
from .contracts import PolicyRecord
from .features import SEMANTIC_DIMENSION

POLICY_VERSION = "bayes-linear-v2:signed:prior=1:noise=1:exploration=1"


def decode(record, extra_keys=()):
    """Restore mutable A/b buffers; callers validate before using uncached state."""
    import numpy as np
    old_keys = record.term_keys if record else ()
    if len(set(old_keys)) != len(old_keys):
        raise ValueError("Duplicate content indices in policy state")
    keys = tuple(old_keys) + tuple(sorted(set(extra_keys) - set(old_keys)))
    dimension = SEMANTIC_DIMENSION + len(keys)
    precision = np.eye(dimension, dtype=np.float64)
    reward = np.zeros(dimension, dtype=np.float64)
    if record:
        old_dim = SEMANTIC_DIMENSION + len(old_keys)
        if len(record.precision) != old_dim * old_dim * 8 or len(record.reward) != old_dim * 8:
            raise ValueError("Invalid policy buffer size")
        precision[:old_dim, :old_dim] = np.frombuffer(record.precision, dtype="<f8").reshape(old_dim, old_dim)
        reward[:old_dim] = np.frombuffer(record.reward, dtype="<f8")
        if record.revision < 0 or record.evidence_count < 0:
            raise ValueError("Invalid policy counters")
    return keys, precision, reward


def unpack(record, extra_keys=()):
    keys, precision, reward = decode(record, extra_keys)
    validate(precision, reward)
    return keys, precision, reward


def validate(precision, reward):
    import numpy as np
    if not np.isfinite(precision).all() or not np.isfinite(reward).all():
        raise ValueError("Non-finite Bayesian state")
    if not np.allclose(precision, precision.T, rtol=1e-10, atol=1e-12):
        raise ValueError("Asymmetric Bayesian precision")
    try:
        return np.linalg.cholesky(precision)
    except np.linalg.LinAlgError as error:
        raise ValueError("Bayesian precision must be positive definite") from error


def _triangular_solve(matrix, values, lower):
    # Vector-only forward/back substitution avoids generic cubic solves.
    import numpy as np
    result = np.empty_like(values)
    if lower:
        for index in range(len(values)):
            result[index] = (values[index] - matrix[index, :index] @ result[:index]) / matrix[index, index]
    else:
        for index in range(len(values) - 1, -1, -1):
            result[index] = (values[index] - matrix[index, index + 1:] @ result[index + 1:]) / matrix[index, index]
    return result


def _posterior_mean(factor, reward):
    import numpy as np
    center = _triangular_solve(factor.T, _triangular_solve(factor, reward, True), False)
    if not np.isfinite(center).all():
        raise ValueError("Non-finite preference center")
    return center


def mean(precision, reward):
    """Return the posterior center without sampling or an exploration term."""
    return _posterior_mean(validate(precision, reward), reward)


def posterior(precision, reward):
    """Validate once and retain both deterministic products for reuse."""
    factor = validate(precision, reward)
    return factor, _posterior_mean(factor, reward)


def draw(factor, center, seed, extra_count=0):
    """Sample a cached posterior, extending unseen axes with independent priors."""
    import numpy as np
    noise = np.random.default_rng(seed).standard_normal(len(center) + extra_count)
    learned = noise[:len(center)] if factor is None else _triangular_solve(factor.T, noise[:len(center)], False)
    parameters = np.concatenate((center + learned, noise[len(center):]))
    if not np.isfinite(parameters).all():
        raise ValueError("Non-finite sampled parameters")
    return parameters


def scoring_parameters(precision, reward, seed=None):
    factor, center = posterior(precision, reward)
    if seed is None:
        return center, center
    # L^-T z has covariance (L L^T)^-1, retaining all feature correlations.
    return center, draw(factor, center, seed)


def sample(precision, reward, seed):
    return scoring_parameters(precision, reward, seed)[1]


def pack(keys, precision, reward, revision, count):
    validate(precision, reward)
    return encode(keys, precision, reward, revision, count)


def encode(keys, precision, reward, revision, count):
    """Serialize A/b after validation; factors and means stay in memory only."""
    return PolicyRecord(revision, tuple(keys), precision.astype("<f8").tobytes(),
                        reward.astype("<f8").tobytes(), count)
