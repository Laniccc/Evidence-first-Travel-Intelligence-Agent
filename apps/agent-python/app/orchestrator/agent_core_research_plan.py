"""Build Agent Core research plans from contract, gate, and S5 selectors."""

from __future__ import annotations

from typing import Any

from app.orchestrator.agent_core_pipeline_gate import ToolVisibility
from app.orchestrator.agent_core_prompt_guidance import agent_core_task_guidance
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.s5_diversified_tool_selector import S5DiversifiedToolSelector
from app.schemas.agent_core import ResearchPlanClaim, ResearchPlanRecord
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState


def build_research_plan(
    state: TravelAgentState,
    *,
    visibility: ToolVisibility | None = None,
) -> ResearchPlanRecord:
    """Create the phase output consumed by S5 and exposed in Store projection."""
    whitelist = visibility.tool_whitelist if visibility else None
    selector = S5DiversifiedToolSelector(state)
    retrieval_plans = selector.build_all_plans(whitelist)
    planning_context = ClaimSearchPlanner.planning_context(state)
    task_class = _safe_task_class(selector)
    claim_plans = _claim_plans_from_state(state, retrieval_plans, whitelist)

    return ResearchPlanRecord(
        run_id=state.query_id,
        task_class=task_class,
        intent_family=_intent_family(state),
        user_goal_summary=_user_goal_summary(state),
        anchor_keywords=list(planning_context.get("anchor_keywords") or []),
        entities=dict(planning_context.get("entities") or {}),
        claim_plans=claim_plans,
        allowed_tools=list(visibility.allowed_tools if visibility else []),
        blocked_tools=list(visibility.blocked_tools if visibility else []),
        source_family_plan=_source_family_plan(state),
        budgets={
            "max_keyword_searches": ClaimSearchPlanner.max_search_attempts(state),
            "must_attempt_claim_count": len(
                [c for c in claim_plans if c.priority == "required" or c.must_attempt]
            ),
        },
        phase_order=[
            "input_contract",
            "research_plan",
            "evidence_acquisition",
            "evidence_review",
            "answer_draft",
            "citation_guard",
            "delivery",
        ],
        notes=_plan_notes(state, visibility, whitelist, task_class),
    )


def _claim_plans_from_state(
    state: TravelAgentState,
    retrieval_plans: dict[str, Any],
    whitelist: ToolWhitelist | None,
) -> list[ResearchPlanClaim]:
    requirements = list(state.response_contract.claim_requirements) if state.response_contract else []
    out: list[ResearchPlanClaim] = []
    seen: set[str] = set()
    selector = S5DiversifiedToolSelector(state)

    for req in requirements:
        claim_type = selector._canonical_claim(req.claim_type)
        plan = retrieval_plans.get(claim_type)
        out.append(
            ResearchPlanClaim(
                claim_type=claim_type,
                claim_family=req.claim_family,
                claim_description=req.claim_description,
                priority=req.priority,
                requires_exact_fact=req.requires_exact_fact,
                requires_live_data=req.requires_live_data,
                freshness=req.freshness,
                allowed_source_types=list(req.allowed_source_types or []),
                source_families=_source_family_plan(state, claim_type=claim_type),
                preferred_tools=list(req.preferred_tools or []),
                forbidden_tools=list(req.forbidden_tools or []),
                sequence_key=plan.sequence_key if plan else None,
                tool_sequence=list(plan.tool_sequence if plan else []),
                must_attempt=list(plan.must_attempt if plan else []),
                optional_tools=list(plan.optional if plan else []),
                max_attempts=ClaimSearchPlanner.max_search_attempts(state),
                model_prior_allowed=req.model_prior_allowed,
                estimation_allowed=req.estimation_allowed,
                missing_behavior=req.missing_behavior,
                notes=_claim_notes(claim_type, whitelist),
            )
        )
        seen.add(claim_type)

    if not out:
        frame = state.semantic_frame
        needs = list(frame.information_needs if frame and frame.information_needs else [])
        if not needs:
            needs = [selector.primary_claim_type()]
        for need in needs:
            claim_type = selector._canonical_claim(str(need))
            if claim_type in seen:
                continue
            plan = retrieval_plans.get(claim_type)
            out.append(
                ResearchPlanClaim(
                    claim_type=claim_type,
                    priority="important",
                    source_families=_source_family_plan(state, claim_type=claim_type),
                    sequence_key=plan.sequence_key if plan else None,
                    tool_sequence=list(plan.tool_sequence if plan else []),
                    must_attempt=list(plan.must_attempt if plan else []),
                    optional_tools=list(plan.optional if plan else []),
                    max_attempts=ClaimSearchPlanner.max_search_attempts(state),
                    notes=_claim_notes(claim_type, whitelist),
                )
            )
            seen.add(claim_type)

    return out


def _safe_task_class(selector: S5DiversifiedToolSelector) -> str:
    try:
        return selector.sequence_key_for_claim(selector.primary_claim_type())
    except Exception:
        return "mixed_advisory"


def _intent_family(state: TravelAgentState) -> str | None:
    profile = state.intent_profile
    primary = getattr(profile, "primary", None) if profile else None
    return primary.value if hasattr(primary, "value") else (str(primary) if primary else None)


def _user_goal_summary(state: TravelAgentState) -> str:
    if state.response_contract and state.response_contract.user_goal_summary:
        return state.response_contract.user_goal_summary
    return state.raw_user_query


def _source_family_plan(state: TravelAgentState, *, claim_type: str | None = None) -> list[str]:
    plan = state.s5_domain_plan
    if not plan:
        return []
    groups = []
    if claim_type and plan.claim_to_domains:
        domains = set(plan.claim_to_domains.get(claim_type) or [])
        for binding in plan.tool_bindings:
            if binding.domain in domains and binding.provider_group.value not in groups:
                groups.append(binding.provider_group.value)
    if groups:
        return groups
    return [group.value for group in plan.provider_groups()]


def _claim_notes(claim_type: str, whitelist: ToolWhitelist | None) -> list[str]:
    notes = [f"claim={claim_type}"]
    if whitelist:
        notes.extend(list(whitelist.policy_notes or [])[:3])
    return notes


def _plan_notes(
    state: TravelAgentState,
    visibility: ToolVisibility | None,
    whitelist: ToolWhitelist | None,
    task_class: str | None = None,
) -> list[str]:
    notes: list[str] = []
    if state.s5_domain_plan:
        notes.extend(state.s5_domain_plan.notes[:4])
    notes.extend(agent_core_task_guidance(state, task_class=task_class)[:6])
    if visibility:
        notes.extend(list(visibility.stop_reasons or [])[:4])
    if whitelist:
        notes.append("tool visibility resolved by PipelineGate")
    return notes
