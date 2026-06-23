from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.place_ambiguity import PlaceAmbiguityInfo


class EntityPolicy(BaseModel):
    requires_disambiguation: bool = False
    disambiguation_reason: str | None = None
    preferred_tools: list[str] = Field(default_factory=list)
    if_multiple_candidates: Literal[
        "ask_clarification", "choose_highest_confidence", "answer_with_limitation"
    ] = "answer_with_limitation"
    if_unresolved: Literal[
        "ask_clarification", "answer_with_limitation", "continue_with_low_confidence"
    ] = "answer_with_limitation"


class ClaimRequirement(BaseModel):
    claim_type: str
    claim_family: str | None = None
    claim_description: str | None = None
    priority: Literal["required", "important", "optional"] = "important"
    requires_exact_fact: bool = False
    requires_live_data: bool = False
    freshness: Literal["real_time", "today", "recent", "seasonal", "stable"] = "recent"
    allowed_source_types: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    model_prior_allowed: bool = False
    estimation_allowed: bool = False
    coverage_rule: str = ""
    missing_behavior: Literal[
        "ask_clarification", "answer_with_limitation", "omit_claim", "refuse_to_guess"
    ] = "answer_with_limitation"


class ToolStrategy(BaseModel):
    initial_tools: list[str] = Field(default_factory=list)
    fallback_tools: list[str] = Field(default_factory=list)
    max_tool_steps: int = 5
    allow_parallel_tools: bool = False


class FallbackPolicy(BaseModel):
    allow_model_prior_fallback: bool = False
    allow_mock_fallback: bool = True
    allow_partial_answer: bool = True
    no_evidence_behavior: Literal[
        "ask_clarification", "answer_with_limitation", "refuse_to_guess"
    ] = "answer_with_limitation"


class ClarificationPolicy(BaseModel):
    should_ask: bool = False
    question: str | None = None
    reason: str | None = None


class CompositionPolicy(BaseModel):
    must_cite_evidence: bool = True
    distinguish_fact_vs_prior: bool = True
    include_tool_failures_when_relevant: bool = True
    forbid_unsupported_claims: bool = True
    answer_style: Literal[
        "direct", "advisory", "comparison", "itinerary", "clarification"
    ] = "direct"


class ResponseContract(BaseModel):
    contract_id: str = Field(default_factory=lambda: str(uuid4()))
    user_goal_summary: str = ""
    gated_search_keywords: list[str] = Field(
        default_factory=list,
        description="S3-gated anchor keywords from S2 semantics for S5 retrieval",
    )
    place_ambiguity_context: PlaceAmbiguityInfo | None = Field(
        default=None,
        description="Ambiguous place hypotheses from S2, forwarded for S5 resolution",
    )
    entity_policy: EntityPolicy = Field(default_factory=EntityPolicy)
    claim_requirements: list[ClaimRequirement] = Field(default_factory=list)
    tool_strategy: ToolStrategy = Field(default_factory=ToolStrategy)
    fallback_policy: FallbackPolicy = Field(default_factory=FallbackPolicy)
    clarification_policy: ClarificationPolicy = Field(default_factory=ClarificationPolicy)
    composition_policy: CompositionPolicy = Field(default_factory=CompositionPolicy)
    overall_risk_level: Literal["low", "medium", "high"] = "medium"
    derived_debug_answer_mode: str | None = None
    limitations_to_add: list[str] = Field(default_factory=list)
