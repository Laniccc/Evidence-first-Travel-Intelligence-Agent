"""Assemble EvidenceBrief from S7 EvidenceDecisionReport."""

from __future__ import annotations

from app.orchestrator.comparison_helpers import enrich_comparison_brief, is_comparison_mode
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

    curated = _merge_filter_candidates_for_refused(state, report, target_label, curated)

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
    fact_decompositions = list(structured.get("fact_decomposition") or [])
    if structured.get("contradiction_presentation_guidance"):
        curation_notes.append(str(structured["contradiction_presentation_guidance"]))
    plan = structured.get("curation_plan") or {}
    if plan.get("rationale"):
        curation_notes.append(str(plan["rationale"]))
    curation_notes.append(report.summary or "S7 deterministic evaluation")

    return EvidenceBrief(
        target_label=target_label,
        curated_claims=curated,
        fact_decompositions=fact_decompositions,
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


def _merge_filter_candidates_for_refused(
    state: TravelAgentState,
    report: EvidenceDecisionReport,
    target_label: str,
    curated: list[CuratedClaimRow],
) -> list[CuratedClaimRow]:
    """When S7 refuses to adopt, still surface relevance-filter rows for S8."""
    refused_types = {
        d.claim_type
        for d in report.claim_decisions
        if d.adoption in {"refuse_to_guess", "ask_clarification"} and not d.adopted_evidence_ids
    }
    if not refused_types:
        return curated

    structured = state.structured_result or {}
    filter_rows = structured.get("curated_claims") or []
    existing = {(row.claim_type, row.evidence_id) for row in curated}
    merged = list(curated)

    for item in filter_rows:
        row = item if isinstance(item, CuratedClaimRow) else CuratedClaimRow.model_validate(item)
        if row.claim_type not in refused_types:
            nearby_refused = refused_types & {
                "nearby_food",
                "nearby_poi",
                "nearby_hotel",
                "nearby_toilet",
                "nearby_parking",
                "nearby_rest_area",
                "nearby_station",
            }
            if nearby_refused and row.claim_type in {"food", "general_fact", "lodging", "place_candidates"}:
                pass
            elif not (
                "elevation" in refused_types
                and row.claim_type in {"travel_advice", "general_fact"}
                and ("海拔" in row.value or "高度" in row.value)
            ):
                continue
        key = (row.claim_type, row.evidence_id)
        if key in existing:
            continue
        merged.append(
            row.model_copy(
                update={
                    "claim_type": (
                        "elevation"
                        if "elevation" in refused_types and row.claim_type == "travel_advice"
                        else row.claim_type
                    ),
                    "confidence": min(float(row.confidence or 0.5), 0.55),
                    "relevance_score": min(float(row.relevance_score or 0.5), 0.55),
                    "rationale": row.rationale or "检索线索（未达官方采纳标准，供参考）",
                }
            )
        )
        existing.add(key)

    merged.sort(key=lambda r: (r.relevance_score, r.confidence), reverse=True)
    return merged[:24]


def build_evidence_brief(state: TravelAgentState, target_label: str) -> EvidenceBrief:
    if state.evidence_decision_report:
        brief = build_evidence_brief_from_report(state, state.evidence_decision_report, target_label)
        if is_comparison_mode(state):
            brief = enrich_comparison_brief(state, brief, target_label)
        return brief

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
    fact_decompositions = list(structured.get("fact_decomposition") or [])
    curation_notes: list[str] = []
    if structured.get("contradiction_presentation_guidance"):
        curation_notes.append(str(structured["contradiction_presentation_guidance"]))
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

    brief = EvidenceBrief(
        target_label=target_label,
        curated_claims=curated,
        fact_decompositions=fact_decompositions,
        excluded_evidence_ids=excluded,
        coverage_gaps=coverage_gaps,
        conflict_notes=conflict_notes,
        overall_confidence=round(overall, 3),
        curation_notes=curation_notes,
    )
    if is_comparison_mode(state):
        brief = enrich_comparison_brief(state, brief, target_label)
    return brief


def apply_evidence_brief(state: TravelAgentState, brief: EvidenceBrief) -> TravelAgentState:
    state.evidence_brief = brief
    state.field_evidence_summary = brief.to_field_evidence_summary()
    structured = dict(state.structured_result or {})
    structured["evidence_brief"] = brief.model_dump()
    state.structured_result = structured
    return state
