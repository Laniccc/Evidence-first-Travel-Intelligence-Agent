"""S7 → S5 gap-filling request and loop state."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


GapPriority = Literal["high", "medium", "low"]


class EvidenceGapRequest(BaseModel):
    gap_id: str = Field(default_factory=lambda: str(uuid4()))
    claim_type: str
    claim_family: str | None = None
    claim_description: str | None = None
    reason: str = ""
    missing_evidence_need: str = ""
    suggested_domains: list[str] = Field(default_factory=list)
    suggested_tools: list[str] = Field(default_factory=list)
    query_templates: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    already_tried_tools: list[str] = Field(default_factory=list)
    failed_tools: list[str] = Field(default_factory=list)
    max_extra_steps: int = 3
    stop_condition: str = "new_relevant_evidence_or_steps_exhausted"
    priority: GapPriority = "medium"
    gap_signature: str = ""

    def ensure_signature(self) -> str:
        if not self.gap_signature:
            tools = ",".join(sorted(self.suggested_tools))
            self.gap_signature = (
                f"{self.claim_type}|{self.claim_family or ''}|{self.missing_evidence_need}|{tools}"
            )
        return self.gap_signature


class EvidenceGapLoopState(BaseModel):
    gap_round: int = 0
    max_gap_rounds: int = 1
    resolved_gap_ids: list[str] = Field(default_factory=list)
    failed_gap_ids: list[str] = Field(default_factory=list)
    gap_signatures: list[str] = Field(default_factory=list)
    evidence_count_before_gap: int = 0
