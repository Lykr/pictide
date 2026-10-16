"""Complete-combination scoring and versioned, reversible feedback contracts."""
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class ScoreTerm:
    text: str
    channel: str = "positive"


@dataclass(frozen=True)
class ScoreCandidate:
    candidate_id: str
    positive: str
    negative: str
    terms: tuple[ScoreTerm, ...]


@dataclass(frozen=True)
class ScoreRequest:
    request_id: str
    user_id: str
    sampling_seed: int
    candidates: tuple[ScoreCandidate, ...]


@dataclass(frozen=True)
class CandidateScore:
    candidate_id: str
    score: float


@dataclass(frozen=True)
class ScoreResult:
    scores: tuple[CandidateScore, ...]
    feature_version: str
    policy_version: str
    state_revision: int


@dataclass(frozen=True)
class FeedbackUpdate:
    user_id: str
    artifact_id: str
    revision: int
    liked: bool
    candidate: ScoreCandidate
    feature_version: str


@dataclass(frozen=True)
class LearningResult:
    state_revision: int
    status: str


@dataclass(frozen=True)
class RecommendationStatus:
    available: bool
    model_version: str
    feature_version: str
    policy_version: str
    error: str | None = None


@dataclass(frozen=True)
class PolicyRecord:
    """Little-endian float64 precision (square) and reward buffers.

    Axes are semantic positive[384], negative[384], then stable term_keys.
    Bytes keep numerical libraries out of the persistence contract.
    """
    revision: int
    term_keys: tuple[str, ...]
    precision: bytes
    reward: bytes
    evidence_count: int


@dataclass(frozen=True)
class PreferenceTerm:
    text: str
    channel: str
    weight: float
    evidence_count: int


@dataclass(frozen=True)
class PreferencesResult:
    available: bool
    error: str | None
    feature_version: str
    state_revision: int
    reset_revision: int
    reset_at: str | None
    evidence_count: int
    term_count: int
    page: int
    page_size: int
    total_pages: int
    terms: tuple[PreferenceTerm, ...]


@dataclass(frozen=True)
class ResetState:
    revision: int = 0
    event_floor: int = 0
    reset_at: str | None = None


@dataclass(frozen=True)
class ResetResult:
    request_id: str
    reset_revision: int
    reset_at: str


class RecommendationStore(Protocol):
    def get_reset_state(self, user_id: str) -> ResetState: ...
    def reset_user(self, user_id: str, request_id: str, expected_reset_revision: int) -> ResetResult: ...
    def load_vectors(self, encoder_version: str, texts: Sequence[str]) -> dict[str, tuple[float, ...]]: ...
    def save_vectors(self, encoder_version: str, vectors: dict[str, tuple[float, ...]]) -> None: ...
    def load_policy(self, user_id: str, feature_version: str) -> PolicyRecord | None: ...
    def evidence_revision(self, user_id: str, artifact_id: str, feature_version: str) -> int: ...
    def load_evidence(self, user_id: str, feature_version: str) -> tuple[FeedbackUpdate, ...]: ...
    def commit_feedback(self, update: FeedbackUpdate, state: PolicyRecord, expected_revision: int) -> bool: ...
    def pending_feedback(self, user_id: str, feature_version: str) -> tuple[FeedbackUpdate, ...]: ...
    def seed_feedback(self, user_id: str, feature_version: str) -> None: ...


class TextEncoder(Protocol):
    version: str
    dimension: int
    def available(self) -> bool: ...
    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class Recommendation(Protocol):
    def preferences(self, user_id: str, page: int = 1) -> PreferencesResult: ...
    def reset_preferences(self, user_id: str, request_id: str, expected_reset_revision: int) -> ResetResult: ...
    def score(self, request: ScoreRequest) -> ScoreResult: ...
    def apply_feedback(self, update: FeedbackUpdate) -> LearningResult: ...
    def status(self) -> RecommendationStatus: ...
