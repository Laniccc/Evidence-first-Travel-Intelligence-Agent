"""Claude agent-style tool definitions for LLM tool selection in S5."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.resolver import (
    agent_tool_definitions_for_allowed,
    catalog_entry,
    enrich_descriptor_fields,
    resolve_s5_task_class,
)
from app.orchestrator.s5_task_tool_catalogs.shared import SHARED_TOOL_CATALOG
from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

# Backward-compatible alias for modules that referenced AGENT_TOOL_SPECS.
AGENT_TOOL_SPECS = SHARED_TOOL_CATALOG


def route_tools_priority() -> list[str]:
    return ["baidu_place_search_mcp", "baidu_route_mcp", "baidu_route_matrix_mcp", "baidu_traffic_mcp"]


__all__ = [
    "AGENT_TOOL_SPECS",
    "AgentToolDefinition",
    "agent_tool_definitions_for_allowed",
    "catalog_entry",
    "enrich_descriptor_fields",
    "resolve_s5_task_class",
    "route_tools_priority",
]
