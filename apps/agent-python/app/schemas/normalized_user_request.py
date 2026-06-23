from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.place_ambiguity import EntityLabel, PlaceAmbiguityCandidate, PlaceAmbiguityInfo


class NormalizedEntity(BaseModel):
    text: str
    normalized_name: str | None = None
    entity_type: Literal[
        "country",
        "region",
        "province",
        "city",
        "district",
        "attraction",
        "landmark",
        "natural_site",
        "station",
        "unknown",
    ] = "unknown"
    country: str | None = None
    region: str | None = None
    city: str | None = None
    source: Literal[
        "llm_understanding",
        "conversation_context",
        "user_explicit",
        "unknown",
    ] = "llm_understanding"
    confidence: float = 0.7
    needs_verification: bool = False
    labels: list[EntityLabel] = Field(
        default_factory=list,
        description="Semantic tags for S3 gating (not hard filters on entity text)",
    )


class NormalizedTimeScope(BaseModel):
    scope: Literal[
        "current",
        "specific_date",
        "month",
        "seasonal",
        "flexible",
        "unknown",
    ] = "unknown"
    reference_date: str | None = None
    months: list[int] = Field(default_factory=list)


class NormalizedUserConstraints(BaseModel):
    party: list[str] = Field(default_factory=list)
    pace: str | None = None
    budget: str | None = None
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class InformationNeedDraft(BaseModel):
    need_type: str
    priority: Literal["required", "high", "medium", "low"] = "medium"
    reason: str = ""


class AnswerPolicyDraft(BaseModel):
    requires_live_data: bool = False
    requires_exact_fact: bool = False
    can_answer_with_model_prior: bool = False
    must_use_official_source: bool = False
    allow_partial_answer: bool = True
    should_add_limitations: bool = True


class NormalizedUserRequest(BaseModel):
    raw_query: str
    rewritten_query: str
    language: str | None = None
    intent_summary: str = ""

    query_scope: Literal[
        "place",
        "city",
        "region",
        "country",
        "route",
        "itinerary",
        "unknown",
    ] = "unknown"

    task_family: Literal[
        "fact_lookup",
        "suitability",
        "comparison",
        "planning",
        "advisory",
        "crowd",
        "weather",
        "transport",
        "food",
        "lodging",
        "unknown",
    ] = "unknown"

    decision_type: Literal[
        "best_time_to_visit",
        "whether_to_go",
        "how_to_choose",
        "risk_check",
        "route_plan",
        "nearby_search",
        "opening_hours",
        "ticket_price",
        "crowd_level",
        "general_advice",
        "unknown",
    ] = "unknown"

    entities: list[NormalizedEntity] = Field(default_factory=list)
    time_scope: NormalizedTimeScope = Field(default_factory=NormalizedTimeScope)
    user_constraints: NormalizedUserConstraints = Field(default_factory=NormalizedUserConstraints)
    information_needs: list[InformationNeedDraft] = Field(default_factory=list)
    answer_policy: AnswerPolicyDraft = Field(default_factory=AnswerPolicyDraft)

    missing_critical_info: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    confidence: float = 0.7
    place_ambiguity: PlaceAmbiguityInfo | None = None
