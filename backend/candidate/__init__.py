"""Candidate domain: read-only cooccurrence library and editable generation presets."""
from .contracts import Candidate, CandidateProvider, TagSnapshot
from .errors import CandidateError
from .provider import CooccurrenceCandidateProvider
from .service import CandidateService

__all__ = ["Candidate", "CandidateProvider", "TagSnapshot", "CandidateError",
           "CooccurrenceCandidateProvider", "CandidateService"]
