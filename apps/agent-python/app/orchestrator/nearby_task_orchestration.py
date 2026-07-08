"""poi_recommendation / NEARBY task-class orchestration (S5 finish hints, compose mode)."""

from __future__ import annotations

from app.orchestrator.information_need_aliases import (
    all_nearby_needs_from_state,
    is_nearby_need,
    nearby_needs_set,
    primary_nearby_need_from_state,
    query_text_from_state,
    resolve_nearby_need,
)
from app.orchestrator.nearby_enrichment_policy import (
    nearby_reputation_satisfied,
    requires_nearby_reputation_signal,
)
from app.orchestrator.nearby_anchor_policy import anchor_place_name, same_scenic_area_sub_poi_ambiguity
from app.orchestrator.nearby_recommendation_policy import actionable_claim_types_for_need
from app.orchestrator.place_disambiguation_guard import extract_place_candidates
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.intent_profile import PrimaryIntent
from app.schemas.user_query import TravelAgentState

_FOOD_ONLY_NEEDS = frozenset(
    {
        "nearby_food",
        "nearby_dining",
        "restaurant_recommendation",
        "food_nearby",
        "food_recommendation",
    }
)


def is_nearby_recommendation_task(state: TravelAgentState) -> bool:
    strategy = state.intent_strategy
    if strategy and strategy.retrieval_mode == "poi_recommendation":
        return True
    if strategy and strategy.primary_intent == PrimaryIntent.NEARBY:
        return True
    frame = state.semantic_frame
    if frame and frame.information_needs and nearby_needs_set(frame.information_needs):
        return True
    contract = state.response_contract
    if contract:
        for req in contract.claim_requirements:
            if req.claim_family == "nearby_recommendation" or is_nearby_need(req.claim_type):
                return True
    task = state.travel_task
    if task and getattr(task, "task_type", None):
        tname = str(getattr(task.task_type, "value", task.task_type))
        if "nearby" in tname.lower() or tname == "food_nearby":
            return True
    return False


def _focus_claim_types_for_need(need: str) -> frozenset[str]:
    return actionable_claim_types_for_need(need)


def count_nearby_actionable_claims(evidence: list, nearby_need: str) -> int:
    focus = _focus_claim_types_for_need(nearby_need)
    n = 0
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        for claim in ev.claims:
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            if ct == ClaimType.PLACE_CANDIDATES.value:
                continue
            if focus and ct not in focus:
                continue
            val = str(claim.value or "").strip()
            if val and val not in {"[]", "{}"}:
                n += 1
    return n


def count_nearby_food_claims(evidence: list) -> int:
    """Backward-compatible helper for food-focused tests."""
    return count_nearby_actionable_claims(evidence, "nearby_food")


def nearby_s5_has_actionable_evidence(state: TravelAgentState) -> bool:
    needs = all_nearby_needs_from_state(state)
    return any(
        count_nearby_actionable_claims(list(state.evidence or []), need) >= 1 for need in needs
    )


def nearby_s5_has_rich_evidence(state: TravelAgentState) -> bool:
    need = primary_nearby_need_from_state(state)
    return count_nearby_actionable_claims(list(state.evidence or []), need) >= 3


def nearby_s5_has_actionable_food_evidence(state: TravelAgentState) -> bool:
    return nearby_s5_has_actionable_evidence(state)


def nearby_s5_has_rich_food_evidence(state: TravelAgentState) -> bool:
    return nearby_s5_has_rich_evidence(state)


def entity_resolution_completed(state: TravelAgentState) -> bool:
    structured = state.structured_result or {}
    for row in structured.get("subagent_results") or []:
        if row.get("subagent") == "entity_resolution_agent":
            return True
    return False


def nearby_s5_may_finish_early(state: TravelAgentState, step: int) -> bool:
    """Allow S5 to finish once anchor + nearby retrieval produced actionable POI evidence."""
    if not is_nearby_recommendation_task(state) or step < 1:
        return False
    if not entity_resolution_completed(state):
        return False
    if not nearby_s5_has_actionable_evidence(state):
        return False
    need = primary_nearby_need_from_state(state)
    if requires_nearby_reputation_signal(state) and not nearby_reputation_satisfied(
        state, list(state.evidence or []), need
    ):
        return False
    return True


def nearby_s5_skip_fact_search(state: TravelAgentState) -> bool:
    """Nearby query with sufficient map evidence — avoid generic review search by default."""
    if not is_nearby_recommendation_task(state):
        return False
    need = primary_nearby_need_from_state(state)
    if requires_nearby_reputation_signal(state):
        if not nearby_reputation_satisfied(state, list(state.evidence or []), need):
            return False
    primary = need
    if primary != "nearby_food" and "review_summary" in (state.semantic_frame.information_needs or [] if state.semantic_frame else []):
        return False
    if primary == "nearby_food":
        frame = state.semantic_frame
        needs = set(frame.information_needs or []) if frame else set()
        text = query_text_from_state(state)
        resolved = {resolve_nearby_need(n, text=text) for n in needs if is_nearby_need(n)}
        if not resolved <= _FOOD_ONLY_NEEDS and "review_summary" in needs:
            return False
    return nearby_s5_has_rich_evidence(state)


def nearby_s5_system_append(state: TravelAgentState) -> str:
    if not is_nearby_recommendation_task(state):
        return ""
    need = primary_nearby_need_from_state(state)
    claim_n = count_nearby_actionable_claims(list(state.evidence or []), need)
    rep_note = ""
    if requires_nearby_reputation_signal(state):
        rep_note = (
            "\n6. User wants口碑/评价 — entity_resolution should enrich top POIs with "
            "baidu_place_detail (rating) and dianping_review when enabled; do not finish until "
            "at least 2 top candidates have rating or review evidence."
        )
    return f"""
## Task class: poi_recommendation (nearby POI / amenity)

Primary nearby need for this query: {need}

Roles for this query:
1. entity_resolution_agent first — anchors place, runs Baidu nearby, then enriches top POIs (detail rating / optional reviews).
2. After entity_resolution, prefer finish_state when map/nearby evidence exists ({claim_n} actionable claims now).
3. Optional fact_search_agent ONLY if nearby evidence is thin (<3 items) OR user explicitly wants 攻略 beyond POI+口碑.
4. Do NOT rotate through unrelated MCP tools; trust entity_resolution nearby retrieval + enrichment.
5. Never call route/weather unless the user asked distance/weather.{rep_note}

finish_state is appropriate when: entity_resolution done AND at least one adoptable nearby claim exists for {need}.
""".strip()


def nearby_s5_planning_context(state: TravelAgentState) -> dict:
    if not is_nearby_recommendation_task(state):
        return {}
    need = primary_nearby_need_from_state(state)
    return {
        "s5_task_class": "poi_recommendation",
        "primary_nearby_need": need,
        "nearby_actionable_claim_count": count_nearby_actionable_claims(list(state.evidence or []), need),
        "nearby_food_claim_count": count_nearby_actionable_claims(list(state.evidence or []), need),
        "entity_resolution_completed": entity_resolution_completed(state),
        "nearby_may_finish_early": nearby_s5_may_finish_early(state, step=99),
        "nearby_skip_fact_search": nearby_s5_skip_fact_search(state),
        "nearby_requires_reputation": requires_nearby_reputation_signal(state),
        "nearby_reputation_satisfied": nearby_reputation_satisfied(
            state, list(state.evidence or []), need
        ),
    }


def should_use_nearby_guided_compose(state: TravelAgentState) -> bool:
    """Hybrid S8: area-level nearby POI list + light disambiguation (nearby task only)."""
    if not is_nearby_recommendation_task(state):
        return False
    if not nearby_s5_has_actionable_evidence(state):
        return False
    candidates = extract_place_candidates(list(state.evidence or []))
    if len(candidates) < 2:
        return False
    anchor = anchor_place_name(state)
    if same_scenic_area_sub_poi_ambiguity(candidates, anchor):
        return True
    from tools.mcp.adapters.baidu_response_parser import candidates_are_ambiguous

    return candidates_are_ambiguous(candidates)


def resolve_nearby_compose_mode(state: TravelAgentState) -> str | None:
    if should_use_nearby_guided_compose(state):
        return "nearby_guided"
    if is_nearby_recommendation_task(state) and state.intent_strategy:
        return state.intent_strategy.compose_mode
    return None
