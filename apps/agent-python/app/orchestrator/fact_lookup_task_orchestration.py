"""strict_fact_lookup task-class orchestration (S5 finish hints, S8 compose mode)."""

from __future__ import annotations

from app.orchestrator.fact_lookup_policy import (
    collect_fact_clues,
    count_actionable_fact_claims,
    fact_need_label,
    has_official_fact_evidence,
    is_fact_lookup_task,
    is_geographic_fact_need,
    primary_fact_need_from_state,
)
from app.schemas.intent_profile import PrimaryIntent
from app.schemas.user_query import TravelAgentState


def fact_lookup_completed(state: TravelAgentState) -> bool:
    structured = state.structured_result or {}
    for row in structured.get("subagent_results") or []:
        if row.get("subagent") == "fact_lookup_agent":
            return True
    return False


def fact_s5_has_actionable_evidence(state: TravelAgentState) -> bool:
    need = primary_fact_need_from_state(state)
    return count_actionable_fact_claims(list(state.evidence or []), need) >= 1


def fact_s5_may_finish_early(state: TravelAgentState, step: int) -> bool:
    if not is_fact_lookup_task(state) or step < 1:
        return False
    if not fact_lookup_completed(state):
        return False
    need = primary_fact_need_from_state(state)
    actionable = count_actionable_fact_claims(list(state.evidence or []), need)
    if actionable >= 1:
        if has_official_fact_evidence(list(state.evidence or []), need):
            return True
        return step >= 1
    return step >= 3


def fact_s5_skip_fact_search(state: TravelAgentState) -> bool:
    """After fact_lookup_agent pipeline, avoid generic fact_search rotation."""
    if not is_fact_lookup_task(state):
        return False
    if not fact_lookup_completed(state):
        return False
    need = primary_fact_need_from_state(state)
    return count_actionable_fact_claims(list(state.evidence or []), need) >= 1


def fact_s5_system_append(state: TravelAgentState) -> str:
    if not is_fact_lookup_task(state):
        return ""
    from app.orchestrator.fact_lookup_anchor_policy import place_scope_note, resolved_place_label

    need = primary_fact_need_from_state(state)
    label = fact_need_label(need)
    n = count_actionable_fact_claims(list(state.evidence or []), need)
    official = has_official_fact_evidence(list(state.evidence or []), need)
    place = resolved_place_label(state)
    scope = place_scope_note(state, need)
    geo_block = ""
    if is_geographic_fact_need(need):
        geo_block = """
Geographic numeric facts (elevation, etc.):
- Anchor entity via geo tools first; then use encyclopedia / structured geo / official reader.
- If first pass lacks numeric claims, delegate follow-up searches (fact_search_agent) with refined queries from evidence gaps — do NOT hardcode peak names.
- finish_state only when required claim is covered OR gap planner reports no productive tool left."""
    scope_line = f"\nPlace scope: {scope}" if scope else ""
    return f"""
## Task class: strict_fact_lookup (hard fact / {need})

Primary fact need: {need} ({label})
Resolved place label: {place}{scope_line}

Roles for this query:
1. **Once** call `fact_lookup_agent` — geo anchor (if city/POI missing) → official-first pipeline.
2. Do NOT rotate unrelated tools (route/weather/nearby/review) unless user explicitly asked.
3. `finish_state` when fact_lookup_agent completed ({n} actionable {label} claims; official={official}).
4. If no official evidence: S8 states「无法确认」; never invent prices/hours/elevation.
5. Never re-call fact_lookup_agent after it appears in subagent_results.{geo_block}

finish_state is appropriate when: fact_lookup_agent completed AND (actionable evidence exists OR elevation pipeline exhausted).
""".strip()


def fact_s5_planning_context(state: TravelAgentState) -> dict:
    if not is_fact_lookup_task(state):
        return {}
    from app.orchestrator.fact_lookup_anchor_policy import place_scope_note, raw_place_label, resolved_place_label

    need = primary_fact_need_from_state(state)
    structured = state.structured_result or {}
    return {
        "s5_task_class": "strict_fact_lookup",
        "primary_fact_need": need,
        "fact_raw_place": raw_place_label(state),
        "fact_resolved_place": resolved_place_label(state),
        "fact_place_scope_note": place_scope_note(state, need),
        "fact_anchor": structured.get("fact_anchor"),
        "fact_actionable_claim_count": count_actionable_fact_claims(list(state.evidence or []), need),
        "fact_lookup_completed": fact_lookup_completed(state),
        "fact_has_official_evidence": has_official_fact_evidence(list(state.evidence or []), need),
        "fact_may_finish_early": fact_s5_may_finish_early(state, step=99),
        "fact_skip_fact_search": fact_s5_skip_fact_search(state),
    }


def should_use_fact_lookup_guided_compose(state: TravelAgentState) -> bool:
    if not is_fact_lookup_task(state):
        return False
    if state.intent_profile and state.intent_profile.primary_intent not in {PrimaryIntent.LOOKUP}:
        if not is_fact_lookup_task(state):
            return False
    return fact_s5_has_actionable_evidence(state) or fact_lookup_completed(state)


def resolve_fact_lookup_compose_mode(state: TravelAgentState) -> str | None:
    if should_use_fact_lookup_guided_compose(state):
        return "fact_lookup_guided"
    if is_fact_lookup_task(state) and state.intent_strategy:
        return state.intent_strategy.compose_mode
    return None
