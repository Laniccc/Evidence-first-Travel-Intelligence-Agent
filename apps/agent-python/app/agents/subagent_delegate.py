"""Recursive S5 sub-agent delegation (sub-agent calls sub-agent)."""

from __future__ import annotations

from typing import Any

from app.schemas.user_query import TravelAgentState

_DELEGATABLE: dict[str, str] = {
    "nearby_anchor_strategy_agent": "nearby_anchor_strategy_agent",
    "entity_resolution_agent": "entity_resolution_agent",
    "fact_lookup_agent": "fact_lookup_agent",
    "fact_search_agent": "fact_search_agent",
    "route_feasibility_agent": "route_feasibility_agent",
    "weather_context_agent": "weather_context_agent",
}


async def delegate_subagent(
    name: str,
    state: TravelAgentState,
    arguments: dict,
    *,
    tools_registry: Any = None,
    prompt_context: dict | None = None,
    parent_subagent: str | None = None,
) -> dict:
    """Invoke a registered S5 sub-agent from within another sub-agent."""
    resolved = _DELEGATABLE.get(name, name)
    args = dict(arguments or {})
    if parent_subagent:
        args.setdefault("parent_subagent", parent_subagent)

    if resolved == "nearby_anchor_strategy_agent":
        from app.agents.nearby_anchor_strategy_agent import NearbyAnchorStrategyAgent

        return await NearbyAnchorStrategyAgent().run(state, args, prompt_context)

    if resolved == "entity_resolution_agent":
        if not tools_registry:
            raise RuntimeError("tools_registry required for entity_resolution_agent delegation")
        from app.agents.entity_resolution_agent import EntityResolutionAgent

        return await EntityResolutionAgent(tools_registry).run(state, args, prompt_context)

    if resolved == "fact_lookup_agent":
        if not tools_registry:
            raise RuntimeError("tools_registry required for fact_lookup_agent delegation")
        from app.agents.fact_lookup_agent import FactLookupAgent

        return await FactLookupAgent(tools_registry).run(state, args, prompt_context)

    if resolved == "fact_search_agent":
        if not tools_registry:
            raise RuntimeError("tools_registry required for fact_search_agent delegation")
        from app.agents.fact_search_agent import FactSearchAgent

        return await FactSearchAgent(tools_registry).run(state, args, prompt_context)

    if resolved == "route_feasibility_agent":
        if not tools_registry:
            raise RuntimeError("tools_registry required for route_feasibility_agent delegation")
        from app.agents.route_feasibility_agent import RouteFeasibilityAgent

        return await RouteFeasibilityAgent(tools_registry).run(state, args, prompt_context)

    if resolved == "weather_context_agent":
        if not tools_registry:
            raise RuntimeError("tools_registry required for weather_context_agent delegation")
        from app.agents.weather_context_agent import WeatherContextAgent

        return await WeatherContextAgent(tools_registry).run(state, args, prompt_context)

    raise ValueError(f"Sub-agent delegation not supported: {name}")
