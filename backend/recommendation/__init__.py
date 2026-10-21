"""Independent complete-combination recommendation service."""
from .encoder import MiniLMEncoder
from .service import RecommendationService

__all__ = ["MiniLMEncoder", "RecommendationService"]
