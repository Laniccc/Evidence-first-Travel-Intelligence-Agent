"""Map S7 adoption + coverage to user-facing ClaimDecision fields."""

from __future__ import annotations

from app.orchestrator.claim_family_registry import claim_family_for_type
from app.orchestrator.search_snippet_policy import evidence_strength_for_claim
from app.schemas.evidence import Evidence
from app.schemas.evidence_decision_report import AdoptionLevel, ClaimDecision


def _structured_adopted_value(decision: ClaimDecision, evidence: list | None) -> str | None:
    if not evidence:
        return None
    ct = decision.claim_type
    family = claim_family_for_type(ct)
    if family == "operation_status" or ct == "opening_hours":
        from app.orchestrator.opening_hours_extractor import extract_opening_hours_from_evidence

        facts = extract_opening_hours_from_evidence(evidence)
        for fact in facts:
            line = fact.summary_line()
            if line:
                return line
    if family == "ticket_booking" or ct in {
        "ticket_price",
        "entrance_ticket_price",
        "boat_ticket_price",
        "shuttle_bus_ticket_price",
        "cable_car_ticket_price",
    }:
        from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_evidence
        from app.orchestrator.ticket_price_audit import preferred_ticket_facts

        facts = preferred_ticket_facts(extract_ticket_price_from_evidence(evidence, claim_type=ct), claim_type=ct)
        for fact in facts:
            line = fact.summary_line()
            if line:
                return line
    return _adopted_text(decision, evidence)


def _adopted_text(decision: ClaimDecision, evidence: list | None) -> str | None:
    if not decision.adopted_evidence_ids or not evidence:
        return None
    for ev in evidence:
        if not isinstance(ev, Evidence):
            continue
        if ev.evidence_id not in decision.adopted_evidence_ids:
            continue
        for claim in ev.claims or []:
            val = str(claim.value or "").strip()
            if val:
                return val
    return None


def _source_strength_summary(decision: ClaimDecision, evidence: list | None) -> dict:
    if not evidence or not decision.adopted_evidence_ids:
        return {}
    summary: dict[str, str] = {}
    for ev in evidence:
        if not isinstance(ev, Evidence):
            continue
        if ev.evidence_id not in decision.adopted_evidence_ids:
            continue
        summary[ev.evidence_id] = evidence_strength_for_claim(ev, decision.claim_type)
    return summary


def adoption_level_from_decision(decision: ClaimDecision) -> AdoptionLevel:
    adoption = decision.adoption
    quality = decision.coverage_quality
    if adoption in {"omit", "refuse_to_guess"} and quality == "none":
        return "no_evidence"
    if adoption == "candidate_only":
        return "candidate_only"
    if adoption == "ask_clarification":
        return "weak"
    if adoption in {"omit", "refuse_to_guess"}:
        return "rejected"
    if quality == "strong" and adoption == "adopt":
        return "strong"
    if quality in {"partial", "weak"} or adoption == "adopt_with_limitation":
        return "partial"
    if quality == "none":
        return "no_evidence"
    return "weak"


def enrich_claim_decision(
    decision: ClaimDecision,
    *,
    evidence: list | None = None,
    claim_id: str | None = None,
) -> ClaimDecision:
    level = adoption_level_from_decision(decision)
    adopted_value = _structured_adopted_value(decision, evidence) or _adopted_text(decision, evidence)
    can_answer = level in {"strong", "partial"} and decision.adoption in {
        "adopt",
        "adopt_with_limitation",
    }
    must_limit = level in {"partial", "candidate_only", "weak", "no_evidence"} or (
        decision.adoption == "adopt_with_limitation"
    )
    missing: list[str] = []
    user_limits: list[str] = []
    internal_limits: list[str] = []
    if level == "no_evidence":
        missing.append(f"official_{decision.claim_type}")
        user_limits.append(_no_evidence_user_message(decision.claim_type))
    elif level == "candidate_only":
        missing.append("official_confirmation")
        user_limits.append(_candidate_only_user_message(decision.claim_type))
    for lim in decision.limitations or []:
        if _is_internal_limitation(lim):
            internal_limits.append(lim)
        else:
            user_limits.append(lim)
    return decision.model_copy(
        update={
            "claim_id": claim_id or decision.claim_id,
            "adoption_level": level,
            "adopted_value": adopted_value,
            "can_answer_directly": can_answer,
            "must_show_limitation": must_limit,
            "missing_evidence": missing,
            "source_strength_summary": _source_strength_summary(decision, evidence),
            "user_visible_limitations": user_limits,
            "internal_debug_limitations": internal_limits,
        }
    )


def _is_internal_limitation(text: str) -> bool:
    blob = str(text or "").lower()
    return any(
        token in blob
        for token in (
            "max_steps",
            "cannot finish",
            "policy reject",
            "configured tools",
            "parse error",
            "provider runtime",
            "missing source url",
            "no_urls_or_search",
        )
    )


def _candidate_only_user_message(claim_type: str) -> str:
    if claim_type == "boat_ticket_price":
        return "未查到官方游船船票价格；以下为第三方/摘要候选，仅供参考。"
    if claim_type in {"ticket_price", "entrance_ticket_price"}:
        return "未查到官方景区门票价格；以下为第三方/摘要候选，仅供参考。"
    if claim_type == "opening_hours":
        return "检索到开放时间相关摘要，但未能读取官方原页确认。"
    return "证据仅为候选来源，未获官方确认。"


def _no_evidence_user_message(claim_type: str) -> str:
    if claim_type == "boat_ticket_price":
        return "未查到可采纳的游船船票价格证据。"
    if claim_type in {"ticket_price", "entrance_ticket_price"}:
        return "未查到官方景区门票价格。"
    if claim_type == "opening_hours":
        return "未能确认开放时间。"
    return "无法确认该事实。"
