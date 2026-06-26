"""Resolve tool cards by S5 task class (retrieval sequence key)."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition
from app.orchestrator.s5_task_tool_catalogs.live_status import LIVE_STATUS_TOOL_CATALOG
from app.orchestrator.s5_task_tool_catalogs.minimal_probe import MINIMAL_PROBE_TOOL_CATALOG
from app.orchestrator.s5_task_tool_catalogs.mixed_advisory import MIXED_ADVISORY_TOOL_CATALOG
from app.orchestrator.s5_task_tool_catalogs.poi_recommendation import POI_RECOMMENDATION_TOOL_CATALOG
from app.orchestrator.s5_task_tool_catalogs.review_first import REVIEW_FIRST_TOOL_CATALOG
from app.orchestrator.s5_task_tool_catalogs.route_first import ROUTE_FIRST_TOOL_CATALOG
from app.orchestrator.s5_task_tool_catalogs.shared import SHARED_TOOL_CATALOG
from app.orchestrator.s5_task_tool_catalogs.strict_fact_lookup import STRICT_FACT_LOOKUP_TOOL_CATALOG
from app.schemas.user_query import TravelAgentState

TASK_TOOL_CATALOGS: dict[str, dict[str, AgentToolDefinition]] = {
    "poi_recommendation": POI_RECOMMENDATION_TOOL_CATALOG,
    "strict_fact_lookup": STRICT_FACT_LOOKUP_TOOL_CATALOG,
    "minimal_probe": MINIMAL_PROBE_TOOL_CATALOG,
    "review_first": REVIEW_FIRST_TOOL_CATALOG,
    "route_first": ROUTE_FIRST_TOOL_CATALOG,
    "live_status": LIVE_STATUS_TOOL_CATALOG,
    "mixed_advisory": MIXED_ADVISORY_TOOL_CATALOG,
}


def resolve_s5_task_class(state: TravelAgentState) -> str:
    from app.orchestrator.s5_diversified_tool_selector import S5DiversifiedToolSelector

    selector = S5DiversifiedToolSelector(state)
    return selector.sequence_key_for_claim(selector.primary_claim_type())


def catalog_entry(tool_name: str, task_class: str | None = None) -> AgentToolDefinition | None:
    if task_class:
        task_spec = TASK_TOOL_CATALOGS.get(task_class, {}).get(tool_name)
        if task_spec is not None:
            return task_spec
    return SHARED_TOOL_CATALOG.get(tool_name)


def enrich_descriptor_fields(
    tool_name: str,
    base_description: str,
    *,
    task_class: str | None = None,
) -> dict:
    spec = catalog_entry(tool_name, task_class=task_class)
    if not spec:
        return {"description": base_description}
    desc = spec.summary
    if base_description and base_description not in desc:
        desc = f"{spec.summary} ({base_description})"
    return {
        "description": desc,
        "when_to_use": spec.when_to_use,
        "when_not_to_use": spec.when_not_to_use,
        "parameters_hint": "; ".join(f"{k}: {v}" for k, v in spec.parameters.items()),
        "prerequisites": spec.prerequisites,
        "satisfies_needs": spec.satisfies_needs,
        "call_order_hint": spec.call_order_hint,
        "s5_task_class": task_class,
    }


def agent_tool_definitions_for_allowed(
    allowed_names: list[str],
    *,
    task_class: str | None = None,
) -> list[dict]:
    out: list[dict] = []
    for name in allowed_names:
        spec = catalog_entry(name, task_class=task_class)
        if spec:
            card = spec.to_prompt_dict()
            if task_class:
                card["s5_task_class"] = task_class
            out.append(card)
        else:
            out.append({"name": name, "summary": name, "when_to_use": [], "parameters": {}})
    return out
