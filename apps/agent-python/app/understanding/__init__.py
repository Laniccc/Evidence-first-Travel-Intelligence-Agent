"""Understanding capability layer.

This package exposes query understanding, intent classification, entity extraction,
and semantic-frame conversion without owning tool execution or answer composition.
"""

from app.understanding.entity_resolution import LLMPlaceEntityExtractor, PlaceMention
from app.understanding.answer_mode_router import AnswerModeRouter
from app.understanding.information_need_aliases import (
    is_nearby_need,
    normalize_information_needs,
    normalize_need,
)
from app.understanding.intent_profile_deriver import IntentProfileDeriver
from app.understanding.intent_classifier import IntentAgent, RegionGateAgent, TravelTaskExtractor
from app.understanding.query_understanding import LLMUnderstandingSubAgent, QueryUnderstandingAgent
from app.understanding.query_rewriter import ContextualQueryRewriter
from app.understanding.semantic_frame import (
    NormalizedRequestToQueryUnderstanding,
    NormalizedRequestToSemanticFrame,
    NormalizedRequestToTravelTask,
    NormalizedRequestToUserGoal,
    SemanticFrameBuilder,
)

__all__ = [
    "AnswerModeRouter",
    "IntentAgent",
    "IntentProfileDeriver",
    "LLMPlaceEntityExtractor",
    "LLMUnderstandingSubAgent",
    "ContextualQueryRewriter",
    "NormalizedRequestToQueryUnderstanding",
    "NormalizedRequestToSemanticFrame",
    "NormalizedRequestToTravelTask",
    "NormalizedRequestToUserGoal",
    "PlaceMention",
    "QueryUnderstandingAgent",
    "RegionGateAgent",
    "SemanticFrameBuilder",
    "TravelTaskExtractor",
    "is_nearby_need",
    "normalize_information_needs",
    "normalize_need",
]
