"""S2 IntentProfile — soft classification hints for S3/S5/S7/S8."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class PrimaryIntent(str, Enum):
    LOOKUP = "lookup"
    ADVISORY = "advisory"
    PLANNING = "planning"
    COMPARISON = "comparison"
    REVIEW_CHECK = "review_check"
    REALTIME_CHECK = "realtime_check"
    NEARBY = "nearby"
    CLARIFICATION = "clarification"


class EvidenceSensitivity(str, Enum):
    HARD_FACT = "hard_fact"
    EVIDENCE_PREFERRED = "evidence_preferred"
    EXPERIENCE_BASED = "experience_based"
    LIVE_REQUIRED = "live_required"
    MODEL_PRIOR_ALLOWED = "model_prior_allowed"


class AnswerStyle(str, Enum):
    DIRECT_FACT = "direct_fact"
    ADVISORY = "advisory"
    ITINERARY = "itinerary"
    COMPARISON = "comparison"
    RECOMMENDATION_LIST = "recommendation_list"
    CLARIFICATION = "clarification"


class IntentProfile(BaseModel):
    primary_intent: PrimaryIntent
    intent_subtypes: list[str] = Field(default_factory=list)
    evidence_sensitivity: EvidenceSensitivity
    answer_style: AnswerStyle
    requires_geo_resolution: bool = True
    requires_official_source: bool = False
    requires_review_signal: bool = False
    requires_route_planning: bool = False
    requires_live_data: bool = False
    confidence: float = 0.7
    derivation: Literal["rules", "llm_patch", "rules+llm"] = "rules"
