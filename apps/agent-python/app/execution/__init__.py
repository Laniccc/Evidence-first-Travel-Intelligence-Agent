"""Tool execution capability layer with lazy public exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "ActionExecutor": ("app.execution.tool_executor", "ActionExecutor"),
    "DataToolVisibilityDecision": (
        "app.execution.agent_core_data_tool_policy",
        "DataToolVisibilityDecision",
    ),
    "DataToolVisibilityPolicy": (
        "app.execution.agent_core_data_tool_policy",
        "DataToolVisibilityPolicy",
    ),
    "EntityResolutionAgent": ("app.execution.entity_resolution", "EntityResolutionAgent"),
    "FactLookupAgent": ("app.execution.fact_lookup_agent", "FactLookupAgent"),
    "FactSearchAgent": ("app.execution.fact_search_agent", "FactSearchAgent"),
    "KeywordSearchAgent": ("app.execution.keyword_search_agent", "KeywordSearchAgent"),
    "RouteFeasibilityAgent": ("app.execution.route_feasibility_agent", "RouteFeasibilityAgent"),
    "RetryPolicy": ("app.execution.retry_policy", "RetryPolicy"),
    "TimeoutPolicy": ("app.execution.timeout_policy", "TimeoutPolicy"),
    "ToolExecutor": ("app.execution.tool_executor", "ToolExecutor"),
    "TravelToolRegistry": ("app.execution.tool_registry", "TravelToolRegistry"),
    "WeatherContextAgent": ("app.execution.weather_context_agent", "WeatherContextAgent"),
    "run_fact_lookup_pipeline": ("app.execution.fact_lookup_pipeline_runner", "run_fact_lookup_pipeline"),
    "run_lookup_phase": ("app.execution.fact_lookup_phase_runner", "run_lookup_phase"),
    "run_nearby_enrichment_after_retrieval": ("app.execution.nearby_enrichment_runner", "run_nearby_enrichment_after_retrieval"),
    "run_nearby_retrieval_after_anchor": ("app.execution.nearby_retrieval_runner", "run_nearby_retrieval_after_anchor"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
