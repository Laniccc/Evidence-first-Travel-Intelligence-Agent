"""Leakage and stale-vector rejection metrics by document version status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class VersionCaseResult(BaseModel):
    case_id: str
    status: Literal["pending", "superseded", "expired", "rejected"]
    returned: bool
    rejected_by_post_filter: bool = False


class VersioningMetrics(BaseModel):
    case_count: int
    expired_leakage_rate: float
    superseded_leakage_rate: float
    non_active_leakage_rate: float
    stale_vector_rejection: float


def grade_versioning(results: list[VersionCaseResult]) -> VersioningMetrics:
    expired = [item for item in results if item.status == "expired"]
    superseded = [item for item in results if item.status == "superseded"]
    leaked = sum(item.returned for item in results)
    rejected = sum(
        not item.returned and item.rejected_by_post_filter
        for item in results
    )
    return VersioningMetrics(
        case_count=len(results),
        expired_leakage_rate=_leakage(expired),
        superseded_leakage_rate=_leakage(superseded),
        non_active_leakage_rate=leaked / len(results) if results else 0.0,
        stale_vector_rejection=rejected / len(results) if results else 0.0,
    )


def _leakage(results: list[VersionCaseResult]) -> float:
    return sum(item.returned for item in results) / len(results) if results else 0.0
