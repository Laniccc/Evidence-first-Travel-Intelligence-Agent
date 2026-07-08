from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CoverageItem(BaseModel):
    claim_type: str
    covered: bool
    evidence_ids: list[str] = Field(default_factory=list)
    missing_reason: str | None = None
    coverage_quality: Literal["none", "weak", "partial", "strong"] = "none"
    can_answer: bool = False
    missing_behavior: str = "answer_with_limitation"


class CoverageReport(BaseModel):
    items: list[CoverageItem] = Field(default_factory=list)
    all_required_covered: bool = False
    can_finish_evidence_planning: bool = False
    answer_should_include_limitations: bool = False
    summary: str = ""
