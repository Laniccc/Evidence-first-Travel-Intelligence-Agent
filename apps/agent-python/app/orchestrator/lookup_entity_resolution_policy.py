"""Stop conditions for entity_resolution during LOOKUP — avoid repeated geo-only loops."""

from __future__ import annotations

from app.orchestrator.fact_lookup_policy import is_fact_lookup_task
from app.schemas.user_query import TravelAgentState

ENTITY_RESOLUTION_MAX_CALLS = 2
ANCHOR_CONFIDENCE_THRESHOLD = 0.70


def count_entity_resolution_calls(state: TravelAgentState) -> int:
    structured = state.structured_result or {}
    n = sum(
        1
        for row in (structured.get("subagent_results") or [])
        if row.get("subagent") == "entity_resolution_agent"
    )
    if n:
        return n
    return sum(
        1
        for trace in state.tool_traces or []
        if str(getattr(trace, "tool_name", "") or "") == "entity_resolution_agent"
        or getattr(trace, "gap_claim_type", None) == "entity_resolution"
    )


def lookup_entity_anchor_satisfied(state: TravelAgentState) -> bool:
    structured = state.structured_result or {}
    anchor = structured.get("fact_anchor") or {}
    if anchor.get("resolved_name"):
        conf = float(anchor.get("confidence") or anchor.get("score") or 0.85)
        if conf >= ANCHOR_CONFIDENCE_THRESHOLD:
            return True
    if structured.get("fact_anchor"):
        return True
    frame = state.semantic_frame
    if frame and frame.entities:
        city = (frame.entities.city or "").strip()
        places = list(frame.entities.places or [])
        country = (frame.entities.country or "").strip()
        if places and city and country:
            return True
        if places and city:
            return True
    return False


def entity_resolution_max_calls(state: TravelAgentState) -> int:
    from app.orchestrator.fact_lookup_policy import primary_fact_need_from_state

    if primary_fact_need_from_state(state) == "ticket_price":
        return 1
    frame = state.semantic_frame
    if frame and frame.entities and (frame.entities.city or "").strip():
        return 1
    return ENTITY_RESOLUTION_MAX_CALLS


def entity_resolution_allowed_for_lookup(state: TravelAgentState) -> bool:
    if not is_fact_lookup_task(state):
        return True
    if lookup_entity_anchor_satisfied(state):
        return False
    return count_entity_resolution_calls(state) < entity_resolution_max_calls(state)
