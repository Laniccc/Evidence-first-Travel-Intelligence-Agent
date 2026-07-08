"""strict_fact_lookup task-class orchestration (LookupResearchChain S5 hints, S8 compose)."""

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
from app.orchestrator.lookup_research_chain import (
    build_lookup_research_context,
    build_retrieval_audit,
    get_lookup_chain,
    lookup_phase_order,
    next_recommended_phase,
)
from app.schemas.intent_profile import PrimaryIntent
from app.schemas.user_query import TravelAgentState


def resolve_fact_s5_task_class(state: TravelAgentState) -> str:
    need = primary_fact_need_from_state(state)
    if need == "ticket_price":
        return "ticket_price_lookup"
    return "strict_fact_lookup"


def fact_lookup_completed(state: TravelAgentState) -> bool:
    """True when at least one fact_lookup phase run completed (not full-chain done)."""
    structured = state.structured_result or {}
    for row in structured.get("subagent_results") or []:
        if row.get("subagent") == "fact_lookup_agent" and not row.get("skipped"):
            return True
    return False


def lookup_chain_audit(state: TravelAgentState):
    chain = get_lookup_chain(state)
    return chain.audit or build_retrieval_audit(state)


def fact_s5_has_actionable_evidence(state: TravelAgentState) -> bool:
    need = primary_fact_need_from_state(state)
    return count_actionable_fact_claims(list(state.evidence or []), need) >= 1


def fact_s5_may_finish_early(state: TravelAgentState, step: int) -> bool:
    if not is_fact_lookup_task(state) or step < 1:
        return False
    need = primary_fact_need_from_state(state)
    if need == "ticket_price":
        from app.orchestrator.retrieval_attempt_ledger import retrieval_complete
        from app.orchestrator.ticket_lookup_attempt_tracker import ticket_lookup_has_price_evidence

        if (
            retrieval_complete(state, "ticket_price")
            and ticket_lookup_has_price_evidence(state, "ticket_price")
            and step >= 2
        ):
            return True
    if need == "opening_hours":
        from app.orchestrator.retrieval_attempt_ledger import retrieval_complete

        if retrieval_complete(state, "opening_hours") and step >= 2:
            return True
    actionable = count_actionable_fact_claims(list(state.evidence or []), need)
    audit = lookup_chain_audit(state)
    report = state.coverage_report
    if report and report.all_required_covered:
        return True
    if audit.recommended_next == "finish" and actionable >= 1:
        return True
    if actionable >= 1 and has_official_fact_evidence(list(state.evidence or []), need):
        return True
    chain = get_lookup_chain(state)
    if "retrieval_audit" in chain.completed_phases and step >= 3:
        return actionable >= 1 or step >= 5
    return step >= 6


def fact_s5_skip_fact_search(state: TravelAgentState) -> bool:
    """Skip generic fact_search only when audit/coverage says research is sufficient."""
    if not is_fact_lookup_task(state):
        return False
    need = primary_fact_need_from_state(state)
    actionable = count_actionable_fact_claims(list(state.evidence or []), need)
    if not actionable:
        return False
    audit = lookup_chain_audit(state)
    if audit.recommended_next == "finish":
        return True
    report = state.coverage_report
    if report and report.all_required_covered:
        return True
    return False


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
    chain_ctx = build_lookup_research_context(state)
    phases = lookup_phase_order(need)
    nxt = next_recommended_phase(state)
    audit = chain_ctx.get("retrieval_audit") or {}
    geo_block = ""
    if is_geographic_fact_need(need):
        geo_block = """
Geographic numeric facts (elevation, etc.):
- Anchor entity via entity_resolution_agent when place ambiguous.
- Use geo_authority source_family (wikidata/wikipedia/osm) in fact_acquisition phase.
- Do NOT hardcode peak names; refine queries from evidence gaps only."""
    scope_line = f"\nPlace scope: {scope}" if scope else ""
    task_class = resolve_fact_s5_task_class(state)
    return f"""
## Task class: {task_class} — LookupResearchChain (hard fact / {need})

Primary fact need: {need} ({label})
Resolved place label: {place}{scope_line}
Phase order: {' → '.join(phases)}
Next recommended phase: {nxt}
Retrieval audit: recommended_next={audit.get('recommended_next', 'continue')}

Roles:
1. **entity_anchor** (if unanchored) → `entity_resolution_agent` once.
2. **official_discovery** / **fact_acquisition** → `fact_lookup_agent` with ONE `lookup_phase` + ONE `source_family` per call.
   Pass arguments: lookup_phase, source_family, claim_target, query_objectives (optional).
3. **fact_search_agent** only when audit recommends continue AND objectives remain untried.
4. `finish_state` when coverage satisfied OR audit.recommended_next=finish OR step budget.
5. Never invent prices/hours/elevation; S8 states「无法确认」when evidence insufficient.
6. Do NOT repeat the same (phase, source_family, objective) — check attempt_signatures.{geo_block}

Current actionable claims: {n} ({label}); official={official}
""".strip()


def fact_s5_planning_context(state: TravelAgentState) -> dict:
    if not is_fact_lookup_task(state):
        return {}
    from app.orchestrator.fact_lookup_anchor_policy import place_scope_note, raw_place_label, resolved_place_label

    need = primary_fact_need_from_state(state)
    structured = state.structured_result or {}
    ctx = build_lookup_research_context(state)
    return {
        "s5_task_class": resolve_fact_s5_task_class(state),
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
        **ctx,
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
