"""LookupClaim — evidence goal layer under ResponseContract."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.response_contract import ClaimRequirement

TargetScope = Literal[
    "whole_place",
    "sub_poi",
    "ticket_product",
    "facility",
    "route_segment",
    "event",
    "policy",
]

ClaimPriority = Literal["required", "important", "optional"]


class LookupClaim(BaseModel):
    claim_id: str = Field(default_factory=lambda: str(uuid4()))
    claim_type: str
    claim_family: str

    target_entity: dict = Field(default_factory=dict)
    target_scope: TargetScope = "whole_place"

    product_or_service: str | None = None
    product_keywords: list[str] = Field(default_factory=list)
    exclude_products: list[str] = Field(default_factory=list)

    time_scope: str = "unknown"
    requires_exact_fact: bool = False
    requires_live_data: bool = False
    model_prior_allowed: bool = True

    preferred_source_families: list[str] = Field(default_factory=list)
    forbidden_source_families: list[str] = Field(default_factory=list)

    evidence_strength_required: str = "partial_allowed"
    extraction_schema: str | None = None
    answer_policy: str | None = None

    priority: ClaimPriority = "required"
    claim_description: str | None = None

    def to_claim_requirement(self) -> ClaimRequirement:
        from app.orchestrator.claim_family_registry import preferred_tools_for_claim

        preferred_tools = preferred_tools_for_claim(self.claim_type)
        freshness = "today" if self.claim_type in {"opening_hours", "current_open_status"} else "recent"
        if self.requires_live_data:
            freshness = "real_time"
        return ClaimRequirement(
            claim_type=self.claim_type,
            claim_family=self.claim_family,
            claim_description=self.claim_description,
            priority=self.priority,
            requires_exact_fact=self.requires_exact_fact,
            requires_live_data=self.requires_live_data,
            freshness=freshness,
            allowed_source_types=["official", "public_web", "map", "tourism_board"],
            preferred_tools=preferred_tools,
            forbidden_tools=["knowledge_prior"] if not self.model_prior_allowed else [],
            model_prior_allowed=self.model_prior_allowed,
            coverage_rule=f"must have explicit evidence for {self.claim_type}",
            missing_behavior="answer_with_limitation",
        )

    @classmethod
    def from_claim_requirement(cls, req: ClaimRequirement) -> LookupClaim:
        from app.orchestrator.claim_family_registry import claim_family_for_type

        family = req.claim_family or claim_family_for_type(req.claim_type)
        return cls(
            claim_type=req.claim_type,
            claim_family=family,
            claim_description=req.claim_description,
            priority=req.priority,
            requires_exact_fact=req.requires_exact_fact,
            requires_live_data=req.requires_live_data,
            model_prior_allowed=req.model_prior_allowed,
        )
