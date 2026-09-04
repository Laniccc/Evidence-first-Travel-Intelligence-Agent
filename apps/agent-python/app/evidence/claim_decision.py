"""Deterministic claim decisions derived from governed retrieval artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, TypeAdapter, field_validator

from app.evidence.coverage_report import CoverageItem, CoverageReport
from app.evidence.evidence_decision_report import ClaimDecision
from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.report import RetrievalReport, RetrievedChunk


class TransientEvidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    attraction_id: str = Field(min_length=1)
    fact_type: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    transient: bool = True
    # Legacy fixtures remain readable; new adapters must use from_verified_payload.
    subtask_id: str | None = Field(default=None, min_length=1)
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    valid_to: AwareDatetime | None = None
    provenance_ref: str | None = Field(default=None, min_length=1)

    @classmethod
    def from_verified_payload(cls, **payload: Any) -> "TransientEvidence":
        evidence = cls(**payload)
        if not all((evidence.subtask_id, evidence.content_hash,
                    evidence.valid_to, evidence.provenance_ref)):
            raise ValueError("new transient evidence requires complete provenance")
        if evidence.retrieved_at.tzinfo is None or evidence.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at requires timezone")
        if evidence.valid_to <= evidence.retrieved_at:
            raise ValueError("evidence validity must follow retrieval")
        if evidence.content_hash != sha256(evidence.content.encode()).hexdigest():
            raise ValueError("content hash mismatch")
        TypeAdapter(HttpUrl).validate_python(evidence.source_url)
        if not evidence.transient:
            raise ValueError("transient evidence cannot declare itself persisted")
        return evidence

    @field_validator("source_url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("source_url must be HTTP(S)")
        return value


class ClaimEvaluation(BaseModel):
    claim_decisions: list[ClaimDecision]
    coverage_report: CoverageReport
    common_fact_types: list[str] = Field(default_factory=list)
    comparison_artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)


def evaluate_claims(
    *,
    plans: list[RetrievalPlan],
    reports: list[RetrievalReport],
    transient_evidence: list[TransientEvidence] | None = None,
) -> ClaimEvaluation:
    reports_by_subtask = {report.subtask_id: report for report in reports}
    live = transient_evidence or []
    decisions: list[ClaimDecision] = []
    coverage_items: list[CoverageItem] = []
    covered_by_subtask: dict[str, set[str]] = {}
    comparison_artifacts: dict[str, dict[str, Any]] = {}

    for plan in plans:
        report = reports_by_subtask.get(plan.subtask_id)
        hits = report.final_hits if report else []
        covered_by_subtask[plan.subtask_id] = set()
        subtask_decisions = []
        expected_types = [item.value for item in plan.fact_types] or ["general_description"]
        for fact_type in expected_types:
            matching = [hit for hit in hits if hit.fact_type == fact_type]
            matching_live = [
                item
                for item in live
                if item.attraction_id in plan.attraction_ids and item.fact_type == fact_type
                # A live snapshot has no declared historical/future validity interval.
                and not plan.require_explicit_temporal_coverage
            ]
            evidence_ids = [hit.chunk_id for hit in matching] + [
                item.evidence_id for item in matching_live
            ]
            claim_id = f"{plan.subtask_id}:{fact_type}"
            if not evidence_ids:
                decision = ClaimDecision(
                    claim_id=claim_id,
                    claim_type=fact_type,
                    required=True,
                    coverage_quality="none",
                    adoption="refuse_to_guess",
                    adoption_level="no_evidence",
                    reason="no_active_evidence",
                    missing_evidence=[fact_type],
                    attraction_id=plan.attraction_ids[0],
                    subtask_id=plan.subtask_id,
                    must_show_limitation=True,
                )
                coverage_items.append(
                    CoverageItem(
                        claim_type=claim_id,
                        covered=False,
                        missing_reason="no_active_evidence",
                        missing_behavior="abstain",
                    )
                )
            else:
                preferred = _preferred_content(matching, matching_live)
                distinct_values = {
                    _normalize(hit.content) for hit in matching
                } | {_normalize(item.content) for item in matching_live}
                conflicted = len(distinct_values) > 1
                decision = ClaimDecision(
                    claim_id=claim_id,
                    claim_type=fact_type,
                    required=True,
                    coverage_quality="partial" if conflicted else "strong",
                    adoption="adopt_with_limitation" if conflicted else "adopt",
                    adoption_level="partial" if conflicted else "strong",
                    adopted_evidence_ids=evidence_ids,
                    conflict_evidence_ids=evidence_ids if conflicted else [],
                    adopted_value=preferred,
                    can_answer_directly=True,
                    must_show_limitation=conflicted,
                    confidence=0.75 if conflicted else 0.95,
                    reason=(
                        "source_conflict_retained_prefer_higher_authority"
                        if conflicted
                        else "active_evidence_supported"
                    ),
                    attraction_id=plan.attraction_ids[0],
                    subtask_id=plan.subtask_id,
                )
                covered_by_subtask[plan.subtask_id].add(fact_type)
                coverage_items.append(
                    CoverageItem(
                        claim_type=claim_id,
                        covered=True,
                        evidence_ids=evidence_ids,
                        coverage_quality="partial" if conflicted else "strong",
                        can_answer=True,
                    )
                )
            decisions.append(decision)
            subtask_decisions.append(decision.model_dump(mode="json"))

        if plan.task_type == "comparison":
            comparison_artifacts[f"comparison:{plan.subtask_id}"] = {
                "attraction_id": plan.attraction_ids[0],
                "claim_decisions": subtask_decisions,
            }

    all_covered = bool(coverage_items) and all(item.covered for item in coverage_items)
    common_fact_types: list[str] = []
    if plans and all(plan.task_type == "comparison" for plan in plans):
        common = set.intersection(
            *(covered_by_subtask[plan.subtask_id] for plan in plans)
        )
        common_fact_types = sorted(common)

    return ClaimEvaluation(
        claim_decisions=decisions,
        coverage_report=CoverageReport(
            items=coverage_items,
            all_required_covered=all_covered,
            can_finish_evidence_planning=all_covered,
            answer_should_include_limitations=any(
                decision.must_show_limitation for decision in decisions
            ),
            summary=(
                "all required claims covered" if all_covered else "required evidence missing"
            ),
        ),
        common_fact_types=common_fact_types,
        comparison_artifacts=comparison_artifacts,
    )


def _preferred_content(
    hits: list[RetrievedChunk], live: list[TransientEvidence]
) -> str:
    if hits:
        return max(hits, key=lambda hit: (hit.source_authority, hit.final_score)).content
    return live[0].content


def _normalize(value: str) -> str:
    return "".join(value.casefold().split())


__all__ = ["ClaimEvaluation", "TransientEvidence", "evaluate_claims"]
