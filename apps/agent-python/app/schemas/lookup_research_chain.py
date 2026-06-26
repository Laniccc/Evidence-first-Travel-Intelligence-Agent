"""Structured state for LOOKUP LookupResearchChain (S5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LookupPhase = Literal[
    "research_frame",
    "entity_anchor",
    "source_plan",
    "official_discovery",
    "official_site_discovery",
    "official_ticket_page_discovery",
    "platform_ticket_candidate",
    "ticket_price_extraction",
    "fact_acquisition",
    "peak_elevation_lookup",
    "retrieval_audit",
]

SourceFamily = Literal[
    "official_operator",
    "government_tourism",
    "ticket_platform",
    "map_candidate",
    "geo_authority",
    "web_reference",
]

AuditRecommendation = Literal["continue", "gap_fill", "finish", "clarify"]


class LookupTargetEntity(BaseModel):
    raw_name: str = ""
    resolved_name: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None
    place_type: str | None = None
    ambiguous: bool = False


class LookupResearchFrame(BaseModel):
    lookup_goal: str = ""
    primary_fact_need: str = ""
    target_entity: LookupTargetEntity = Field(default_factory=LookupTargetEntity)
    source_hypotheses: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)


class SourcePlanItem(BaseModel):
    source_family: SourceFamily
    purpose: str = ""
    tool_candidates: list[str] = Field(default_factory=list)


class LookupQueryObjective(BaseModel):
    objective: str = ""
    source_family: SourceFamily = "web_reference"
    query_intent: str = ""
    anchor_terms: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    avoid_as_final: list[str] = Field(default_factory=list)
    search_query: str | None = None

    def signature(self) -> str:
        terms = "|".join(self.anchor_terms[:6])
        return f"{self.source_family}:{self.objective}:{terms}"


class RetrievalAudit(BaseModel):
    entity_anchored: bool = False
    official_source_attempted: bool = False
    official_fact_found: bool = False
    platform_candidate_found: bool = False
    conflict_possible: bool = False
    recommended_next: AuditRecommendation = "continue"


class LookupResearchChainState(BaseModel):
    current_phase: LookupPhase = "research_frame"
    frame: LookupResearchFrame | None = None
    source_plan: list[SourcePlanItem] = Field(default_factory=list)
    query_objectives: list[LookupQueryObjective] = Field(default_factory=list)
    audit: RetrievalAudit | None = None
    completed_phases: list[LookupPhase] = Field(default_factory=list)
    attempt_signatures: list[str] = Field(default_factory=list)
