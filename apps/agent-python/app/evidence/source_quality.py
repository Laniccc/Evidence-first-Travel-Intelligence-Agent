"""Source quality scoring for evidence objects."""

from pydantic import BaseModel, Field

from app.evidence.evidence_model import DataFreshness, Evidence, SourceType


class SourceQualityResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


_SOURCE_TYPE_SCORES: dict[SourceType, float] = {
    SourceType.OFFICIAL: 0.95,
    SourceType.MAP: 0.85,
    SourceType.WEATHER_API: 0.85,
    SourceType.TRANSIT_API: 0.82,
    SourceType.TICKET_PLATFORM: 0.78,
    SourceType.REVIEW_PLATFORM: 0.72,
    SourceType.FOOD_PLATFORM: 0.70,
    SourceType.LODGING_PLATFORM: 0.70,
    SourceType.WEB: 0.62,
    SourceType.BLOG: 0.45,
    SourceType.SOCIAL: 0.40,
    SourceType.MODEL_PRIOR: 0.30,
    SourceType.UNKNOWN: 0.35,
}

_FRESHNESS_ADJUSTMENTS: dict[DataFreshness, float] = {
    DataFreshness.LIVE: 0.05,
    DataFreshness.RECENT: 0.0,
    DataFreshness.UNKNOWN: -0.05,
    DataFreshness.STALE: -0.15,
}


def score_source_quality(evidence: Evidence) -> SourceQualityResult:
    base_score = _SOURCE_TYPE_SCORES.get(evidence.source_type, 0.35)
    score = base_score + _FRESHNESS_ADJUSTMENTS.get(evidence.data_freshness, 0.0)
    score = min(1.0, max(0.0, round(score * evidence.confidence, 3)))

    reasons = [f"source_type:{evidence.source_type.value}"]
    reasons.append(f"freshness:{evidence.data_freshness.value}")
    if not evidence.source_url:
        reasons.append("missing_source_url")
    if evidence.limitations:
        reasons.append("has_limitations")
    return SourceQualityResult(score=score, reasons=reasons)
