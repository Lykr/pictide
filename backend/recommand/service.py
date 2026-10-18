"""Combination scoring and reversible, revision-checked signed feedback."""
from collections import Counter
import json
from threading import RLock

from ..contracts.recommendation import (CandidateScore, LearningResult, PreferenceTerm, PreferencesResult,
                                        RecommendationStatus, ScoreResult)
from .features import (SEMANTIC_DIMENSION, FeatureEncoder, content_key, dense_features,
                       feature_version, validate_candidate)
from . import policy


class RecommendationService:
    def __init__(self, store, encoder):
        self.store = store
        self.encoder = encoder
        self.features = FeatureEncoder(store, encoder)
        self._lock = RLock()

    def status(self):
        try:
            available = bool(self.encoder.available())
            if self.encoder.dimension != 384:
                available = False
                error = "Recommendation requires a 384-dimensional encoder"
            else:
                error = None if available else getattr(self.encoder, "error", None) or "Text encoder unavailable"
            version = self.encoder.version
            return RecommendationStatus(available, version, feature_version(version), policy.POLICY_VERSION, error)
        except Exception as error:
            version = getattr(self.encoder, "version", "unavailable")
            return RecommendationStatus(False, version, feature_version(version), policy.POLICY_VERSION, str(error))

    def _require_available(self):
        status = self.status()
        if not status.available:
            raise RuntimeError(status.error)
        return status.feature_version

    @staticmethod
    def _identity(value, name):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(name + " must be non-empty text")

    def preferences(self, user_id, page=1):
        """Read a coherent posterior center without encoding, sampling or learning."""
        self._identity(user_id, "user_id")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        with self._lock:
            status = self.status()
            reset = self.store.get_reset_state(user_id)
            def result(available, error=None, revision=0, count=0, terms=()):
                page_size = 15
                total_pages = max(1, (len(terms) + page_size - 1) // page_size)
                current = min(page, total_pages)
                return PreferencesResult(available, error, status.feature_version, revision,
                    reset.revision, reset.reset_at, count, len(terms), current, page_size, total_pages,
                    tuple(terms[(current - 1) * page_size:current * page_size]))
            if not status.available:
                return result(False, status.error)
            try:
                # Existing store reads each use one transaction. Revision checks
                # detect interleaved atomic feedback commits or resets, including
                # reset followed by a new policy with the same numeric revision.
                for _ in range(5):
                    reset = self.store.get_reset_state(user_id)
                    record = self.store.load_policy(user_id, status.feature_version)
                    evidence = self.store.load_evidence(user_id, status.feature_version)
                    after = self.store.load_policy(user_id, status.feature_version)
                    after_reset = self.store.get_reset_state(user_id)
                    if reset == after_reset and ((record is None and after is None) or (
                            record is not None and after is not None and record.revision == after.revision)):
                        break
                else:
                    reset = after_reset
                    return result(False, "偏好正在更新，请重试。")
                active = [item for item in evidence if item.value is not None]
                if record is None:
                    if active:
                        raise ValueError("Missing learned policy")
                    return result(True)
                if record.evidence_count != len(active):
                    raise ValueError("Preference evidence count does not match state")
                counts = Counter()
                for item in active:
                    validate_candidate(item.candidate)
                    counts.update({content_key(term.text, term.channel) for term in item.candidate.terms})
                keys, precision, reward = policy.unpack(record)
                if not counts.keys() <= set(keys):
                    raise ValueError("Missing preference content indices")
                center = policy.mean(precision, reward)
                terms = []
                for index, key in enumerate(keys):
                    if counts[key]:
                        channel, text = json.loads(key)
                        terms.append(PreferenceTerm(text, channel, float(center[SEMANTIC_DIMENSION + index]), counts[key]))
                terms.sort(key=lambda term: (-term.weight, term.channel, term.text))
                return result(True, revision=record.revision, count=len(active), terms=terms)
            except (ValueError, TypeError, KeyError):
                # Viewing is read-only: scoring/learning own derived-state
                # recovery. Never synthesize misleading weights on this path.
                return result(False, "学习状态暂不可读取，请在下次反馈后重试，或重置偏好。")

    def reset_preferences(self, user_id, request_id, expected_reset_revision):
        self._identity(user_id, "user_id")
        self._identity(request_id, "request_id")
        if (isinstance(expected_reset_revision, bool) or not isinstance(expected_reset_revision, int)
                or expected_reset_revision < 0):
            raise ValueError("expected_reset_revision must be a non-negative integer")
        with self._lock:
            return self.store.reset_user(user_id, request_id, expected_reset_revision)

    def score(self, request):
        with self._lock:
            self._identity(request.request_id, "request_id")
            self._identity(request.user_id, "user_id")
            if isinstance(request.sampling_seed, bool) or not isinstance(request.sampling_seed, int) or request.sampling_seed < 0:
                raise ValueError("sampling_seed must be a non-negative integer")
            if request.strategy not in ("thompson", "mean"):
                raise ValueError("strategy must be thompson or mean")
            for candidate in request.candidates:
                validate_candidate(candidate)
            ids = [c.candidate_id for c in request.candidates]
            if len(set(ids)) != len(ids):
                raise ValueError("candidate_id must be unique within a request")
            version = self._require_available()
            prepared = self.features.prepare(request.candidates)
            record = self.store.load_policy(request.user_id, version)
            if record is None:
                evidence = self.store.load_evidence(request.user_id, version)
                if evidence:
                    record = self._rebuilt_record(request.user_id, version, None, evidence)
            if not prepared:
                return ScoreResult((), version, policy.POLICY_VERSION, record.revision if record else 0)
            extra_keys = {key for _, exact in prepared for key in exact}
            try:
                keys, precision, reward = policy.unpack(record, extra_keys)
            except ValueError:
                record = self._rebuilt_record(request.user_id, version, record)
                keys, precision, reward = policy.unpack(record, extra_keys)
            center, parameters = policy.scoring_parameters(precision, reward,
                request.sampling_seed if request.strategy == "thompson" else None)
            vectors = dense_features(prepared, keys)
            means = vectors @ center
            values = means if request.strategy == "mean" else vectors @ parameters
            import numpy as np
            if not np.isfinite(values).all() or not np.isfinite(means).all():
                raise ValueError("Non-finite recommendation score")
            minimum, maximum = self.store.observe_score_range(request.user_id, version, policy.POLICY_VERSION,
                                                             float(means.min()), float(means.max()))
            return ScoreResult(tuple(CandidateScore(c.candidate_id, float(v)) for c, v in zip(request.candidates, values)),
                               version, policy.POLICY_VERSION, record.revision if record else 0, minimum, maximum)

    def _rebuilt_record(self, user_id, version, record, evidence=None):
        import numpy as np
        evidence = self.store.load_evidence(user_id, version) if evidence is None else evidence
        active = [item for item in evidence if item.value is not None]
        prepared = self.features.prepare([item.candidate for item in active])
        keys = tuple(dict.fromkeys(record.term_keys if record else ()))
        extras = {key for _, exact in prepared for key in exact}
        keys += tuple(sorted(extras - set(keys)))
        dimension = 768 + len(keys)
        precision = np.eye(dimension, dtype=np.float64)
        reward = np.zeros(dimension, dtype=np.float64)
        vectors = dense_features(prepared, keys)
        for item, vector in zip(active, vectors):
            precision += np.outer(vector, vector)
            reward += item.value * vector
        return policy.pack(keys, precision, reward, record.revision if record else 0, len(active))

    def apply_feedback(self, update):
        with self._lock:
            self._identity(update.user_id, "user_id")
            self._identity(update.artifact_id, "artifact_id")
            if isinstance(update.revision, bool) or not isinstance(update.revision, int) or update.revision < 1:
                raise ValueError("Feedback revision must be a positive integer")
            if update.value is not None and (type(update.value) is not int or update.value not in (-1, 1)):
                raise ValueError("Feedback value must be 1, -1 or null")
            validate_candidate(update.candidate)
            status = self.status()
            version = status.feature_version
            if not status.available or update.feature_version != version:
                return LearningResult(0, "pending")
            import numpy as np
            for _ in range(8):
                record = self.store.load_policy(update.user_id, version)
                revision = record.revision if record else 0
                if update.revision <= self.store.get_reset_state(update.user_id).event_floor:
                    return LearningResult(revision, "unchanged")
                if self.store.evidence_revision(update.user_id, update.artifact_id, version) >= update.revision:
                    return LearningResult(revision, "unchanged")
                evidence = self.store.load_evidence(update.user_id, version)
                if record is None and evidence:
                    record = self._rebuilt_record(update.user_id, version, None, evidence)
                previous = next((item for item in evidence if item.artifact_id == update.artifact_id), None)
                if previous and previous.revision >= update.revision:
                    return LearningResult(revision, "unchanged")
                prepared = self.features.prepare([item.candidate for item in (previous, update) if item is not None and item.value is not None])
                extras = {key for _, exact in prepared for key in exact}
                try:
                    keys, precision, reward = policy.unpack(record, extras)
                    count = record.evidence_count if record else 0
                    vectors = iter(dense_features(prepared, keys))
                    for sign, item in ((-1, previous), (1, update)):
                        if item is not None and item.value is not None:
                            vector = next(vectors)
                            precision += sign * np.outer(vector, vector)
                            reward += sign * item.value * vector
                            count += sign
                    if count < 0:
                        raise ValueError("Invalid evidence count")
                    state = policy.pack(keys, precision, reward, revision + 1, count)
                except ValueError:
                    remaining = [item for item in evidence if item.artifact_id != update.artifact_id] + [update]
                    rebuilt = self._rebuilt_record(update.user_id, version, record, remaining)
                    state = type(rebuilt)(revision + 1, rebuilt.term_keys, rebuilt.precision, rebuilt.reward, rebuilt.evidence_count)
                if self.store.commit_feedback(update, state, revision):
                    return LearningResult(state.revision, "applied")
            return LearningResult(revision, "pending")
