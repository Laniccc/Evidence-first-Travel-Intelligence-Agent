"""Assemble EvidenceBrief from S7 EvidenceDecisionReport."""

from __future__ import annotations

from app.schemas.evidence import Evidence
from app.schemas.evidence_brief import CuratedClaimRow, EvidenceBrief
from app.schemas.evidence_decision_report import ClaimDecision, EvidenceDecisionReport
from app.schemas.user_query import TravelAgentState


_ADOPTABLE = frozenset({"adopt", "adopt_with_limitation", "candidate_only"})


def build_evidence_brief_from_report(
    state: TravelAgentState,
    report: EvidenceDecisionReport,
    target_label: str,
) -> EvidenceBrief:
    ev_by_id = {ev.evidence_id: ev for ev in state.evidence if isinstance(ev, Evidence)}
    curated: list[CuratedClaimRow] = []
    excluded = [r.evidence_id for r in report.rejected_evidence]

    for decision in report.claim_decisions:
        if decision.adoption not in _ADOPTABLE:
            continue
        for eid in decision.adopted_evidence_ids:
            ev = ev_by_id.get(eid)
            if not ev:
                continue
            value = _claim_value_for(ev, decision.claim_type)
            if not value:
                continue
            curated.append(
                CuratedClaimRow(
                    claim_type=decision.claim_type,
                    value=value,
                    evidence_id=eid,
                    source_name=ev.source_name,
                    source_url=ev.source_url,
                    confidence=decision.confidence,
                    relevance_score=decision.confidence,
                    rationale=decision.reason,
                    place_name=ev.place_name or target_label,
                )
            )

    coverage_gaps: list[str] = []
    for decision in report.claim_decisions:
        if decision.coverage_quality in {"none", "weak"} or decision.adoption in {
            "refuse_to_guess",
            "ask_clarification",
            "candidate_only",
        }:
            coverage_gaps.append(
                f"{decision.claim_type}: {decision.adoption} (quality={decision.coverage_quality})"
            )
    for gap in report.evidence_gap_requests:
        coverage_gaps.append(f"gap pending: {gap.claim_type} ({gap.reason})")

    conflict_notes = [c.conflict_note for c in report.conflicts if c.conflict_note]
    curation_notes: list[str] = []
    structured = state.structured_result or {}
    plan = structured.get("curation_plan") or {}
    if plan.get("rationale"):
        curation_notes.append(str(plan["rationale"]))
    curation_notes.append(report.summary or "S7 deterministic evaluation")

    return EvidenceBrief(
        target_label=target_label,
        curated_claims=curated,
        excluded_evidence_ids=excluded,
        coverage_gaps=coverage_gaps,
        conflict_notes=conflict_notes,
        overall_confidence=report.overall_confidence,
        curation_notes=curation_notes,
    )


def _claim_value_for(ev: Evidence, claim_type: str) -> str:
    for claim in ev.claims:
        ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
        if ct in claim_type or claim_type in ct:
            return str(claim.value)
    if ev.claims:
        return str(ev.claims[0].value)
    return ""


def build_evidence_brief(state: TravelAgentState, target_label: str) -> EvidenceBrief:
    if state.evidence_decision_report:
        return build_evidence_brief_from_report(state, state.evidence_decision_report, target_label)

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
    if state.coverage_report:
        for item in state.coverage_report.items:
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
