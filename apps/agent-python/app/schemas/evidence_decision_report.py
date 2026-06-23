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
