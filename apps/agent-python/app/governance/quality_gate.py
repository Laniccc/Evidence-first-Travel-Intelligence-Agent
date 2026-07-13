"""Quality gate models for Agent outputs."""

from pydantic import BaseModel, Field


class SourceQualityReport(BaseModel):
    checked_sources: int = Field(default=0, ge=0)
    average_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    low_quality_source_ids: list[str] = Field(default_factory=list)


class QualityGateResult(BaseModel):
    passed: bool
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)

    @classmethod
    def from_threshold(
        cls,
        score: float,
        *,
        threshold: float,
        reasons: list[str] | None = None,
    ) -> "QualityGateResult":
        return cls(passed=score >= threshold, score=score, reasons=list(reasons or []))
