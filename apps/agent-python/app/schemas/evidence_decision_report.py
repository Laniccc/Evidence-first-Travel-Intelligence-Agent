"""S7 deterministic evidence evaluation output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CoverageQuality = Literal["none", "weak", "partial", "strong"]
AdoptionDecision = Literal[
    "adopt",
    "adopt_with_limitation",
    "candidate_only",
    "ask_clarification",
    "omit",
    "refuse_to_guess",
]

AdoptionLevel = Literal[
    "strong",
    "partial",
    "candidate_only",
    "weak",
    "rejected",
    "no_evidence",
]


class ClaimDecision(BaseModel):
    claim_type: str
    claim_family: str | None = None
    claim_description: str | None = None
    required: bool = False
    coverage_quality: CoverageQuality = "none"
    adoption: AdoptionDecision = "omit"
    adopted_evidence_ids: list[str] = Field(default_factory=list)
    rejected_evidence_ids: list[str] = Field(default_factory=list)
    supporting_tool_names: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    limitations: list[str] = Field(default_factory=list)
    adoption_level: AdoptionLevel | None = None
    adopted_value: str | None = None
    can_answer_directly: bool = False
    must_show_limitation: bool = False
    missing_evidence: list[str] = Field(default_factory=list)
    claim_id: str | None = None
    source_strength_summary: dict = Field(default_factory=dict)
    user_visible_limitations: list[str] = Field(default_factory=list)
    internal_debug_limitations: list[str] = Field(default_factory=list)

    @property
    def evidence_ids(self) -> list[str]:
        return list(self.adopted_evidence_ids)


class SourceRanking(BaseModel):
    claim_type: str
    evidence_id: str
    source_name: str | None = None
    source_type: str | None = None
    score: float = 0.0
    rank_reason: str = ""


class EvidenceConflict(BaseModel):
    claim_type: str
    conflict_type: str
    evidence_ids: list[str] = Field(default_factory=list)
    preferred_evidence_id: str | None = None
    conflict_note: str = ""


class RejectedEvidence(BaseModel):
    evidence_id: str
    claim_type: str | None = None
    reason: str = ""


from app.schemas.evidence_gap_request import EvidenceGapRequest


class EvidenceDecisionReport(BaseModel):
    claim_decisions: list[ClaimDecision] = Field(default_factory=list)
    source_rankings: list[SourceRanking] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    rejected_evidence: list[RejectedEvidence] = Field(default_factory=list)
    evidence_gap_requests: list[EvidenceGapRequest] = Field(default_factory=list)
    overall_confidence: float = 0.0
    summary: str | None = None
