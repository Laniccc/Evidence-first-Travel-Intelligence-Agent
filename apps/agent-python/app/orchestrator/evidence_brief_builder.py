"""Assemble EvidenceBrief from S7 curation artifacts."""

from __future__ import annotations

from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker
from app.schemas.evidence_brief import CuratedClaimRow, EvidenceBrief
from app.schemas.user_query import TravelAgentState


def build_evidence_brief(state: TravelAgentState, target_label: str) -> EvidenceBrief:
    structured = state.structured_result or {}
    curated_raw = structured.get("curated_claims") or []
    curated: list[CuratedClaimRow] = []
    for item in curated_raw:
        if isinstance(item, CuratedClaimRow):
            curated.append(item)
        elif isinstance(item, dict):
            curated.append(CuratedClaimRow.model_validate(item))

    excluded = list(structured.get("excluded_evidence_ids") or [])
    conflict_notes = list(structured.get("conflict_notes") or [])
    curation_notes: list[str] = []
    plan = structured.get("curation_plan") or {}
    if plan.get("rationale"):
        curation_notes.append(str(plan["rationale"]))

    coverage_gaps: list[str] = []
    if state.response_contract:
        report = state.coverage_report or EvidenceCoverageChecker().check(
            state.response_contract, state.evidence, state.tool_traces
        )
        state.coverage_report = report
        for item in report.items:
            if not item.covered:
                coverage_gaps.append(
                    f"{item.claim_type} uncovered (quality={item.coverage_quality})"
                )

    overall = 0.0
    if curated:
        overall = sum(c.confidence * c.relevance_score for c in curated) / len(curated)

    return EvidenceBrief(
        target_label=target_label,
        curated_claims=curated,
        excluded_evidence_ids=excluded,
        coverage_gaps=coverage_gaps,
        conflict_notes=conflict_notes,
        overall_confidence=round(overall, 3),
        curation_notes=curation_notes,
    )


def apply_evidence_brief(state: TravelAgentState, brief: EvidenceBrief) -> TravelAgentState:
    state.evidence_brief = brief
    state.field_evidence_summary = brief.to_field_evidence_summary()
    structured = dict(state.structured_result or {})
    structured["evidence_brief"] = brief.model_dump()
    state.structured_result = structured
    return state
