"""Framework-independent candidate identity and historical tag meaning."""
from dataclasses import dataclass
import hashlib
import json
from typing import Protocol, Sequence


@dataclass(frozen=True)
class TagSnapshot:
    """Freeze historical text, channel and categories independently of current rules."""
    source_id: str
    id: str
    text: str
    categories: tuple[str, ...] = ()
    channel: str = "positive"

    @property
    def content_revision(self) -> str:
        meaning = json.dumps({"text": self.text, "channel": self.channel}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(meaning.encode("utf-8")).hexdigest()

    @property
    def feature_key(self) -> tuple[str, str, str]:
        return (self.source_id, self.id, self.content_revision)


@dataclass(frozen=True)
class Candidate:
    id: str
    positive: str
    negative: str
    features: tuple[tuple[str, float], ...] = ()
    terms: tuple[TagSnapshot, ...] = ()


class CandidateProvider(Protocol):
    def generate(self, context: dict, constraints: dict) -> Sequence[Candidate]: ...
