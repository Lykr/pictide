"""Full-covariance, signed-evidence Bayesian linear policy."""
from ..contracts.recommendation import PolicyRecord
from .features import SEMANTIC_DIMENSION

POLICY_VERSION = "bayes-linear-v2:signed:prior=1:noise=1:exploration=1"


def unpack(record, extra_keys=()):
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


def sample(precision, reward, seed):
    import numpy as np
    factor = validate(precision, reward)
    center = _posterior_mean(factor, reward)
    noise = np.random.default_rng(seed).standard_normal(len(reward))
    # L^-T z has covariance (L L^T)^-1, retaining all feature correlations.
    parameters = center + _triangular_solve(factor.T, noise, False)
    if not np.isfinite(parameters).all():
        raise ValueError("Non-finite sampled parameters")
    return parameters


def pack(keys, precision, reward, revision, count):
    validate(precision, reward)
    return PolicyRecord(revision, tuple(keys), precision.astype("<f8").tobytes(),
                        reward.astype("<f8").tobytes(), count)
