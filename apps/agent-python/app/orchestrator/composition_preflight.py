"""S8 preflight: do not let premature S5 place clarification block composition."""

from __future__ import annotations

from app.schemas.user_query import TravelAgentState

_ACTIONABLE_ADOPTIONS = frozenset({"adopt", "adopt_with_limitation", "candidate_only"})


def is_premature_place_clarification(state: TravelAgentState) -> bool:
    if not (state.final_response or "").strip():
        return False
    if state.next_state == "clarification_response":
        return True
    if "place_disambiguation" in state.limitations:
        return True
    structured = state.structured_result or {}
    if structured.get("place_disambiguation_pending"):
        return True
    qu = state.query_understanding
    if qu and qu.needs_clarification and qu.clarification_question == state.final_response:
        return True
    return False


def has_actionable_claim_decisions(state: TravelAgentState) -> bool:
    report = state.evidence_decision_report
    if report and any(d.adoption in _ACTIONABLE_ADOPTIONS for d in report.claim_decisions):
        return True
    brief = state.evidence_brief
    return bool(brief and brief.curated_claims)


def should_compose_over_clarification(state: TravelAgentState) -> bool:
    return is_premature_place_clarification(state) and has_actionable_claim_decisions(state)


def clear_premature_clarification_for_composition(state: TravelAgentState) -> bool:
    """Drop S5 clarification draft when S7 already has adoptable rows."""
    if not should_compose_over_clarification(state):
        return False
    state.final_response = ""
    if state.next_state == "clarification_response":
        state.next_state = None
    if state.query_understanding:
        state.query_understanding.needs_clarification = False
    return True
