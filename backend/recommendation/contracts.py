"""Recommendation uses shared contracts, without candidate dependencies."""
from ..contracts.recommendation import Recommendation, RecommendationStore, TextEncoder

__all__ = ["Recommendation", "RecommendationStore", "TextEncoder"]
