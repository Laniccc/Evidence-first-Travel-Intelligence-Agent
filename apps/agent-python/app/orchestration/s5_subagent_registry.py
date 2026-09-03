"""Compatibility profiles for the two bounded evidence acquisition helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class S5SubagentProfile:
    name: str
    summary: str
    when_to_use: list[str]
    tool_priority: list[str]
    satisfies_needs: list[str] = field(default_factory=list)
    delegatable_subagents: list[str] = field(default_factory=list)


S5_SUBAGENT_PROFILES = {
    "fact_lookup_agent": S5SubagentProfile(
        name="fact_lookup_agent",
        summary="Fill one evidence gap from an authoritative source.",
        when_to_use=["The managed knowledge corpus lacks a required hard fact."],
        tool_priority=["search_mcp", "official_source_discovery_mcp", "official_page_reader_mcp"],
        satisfies_needs=["ticket_price", "opening_hours", "visitor_notice", "accessibility"],
    ),
    "entity_resolution_agent": S5SubagentProfile(
        name="entity_resolution_agent",
        summary="Resolve an attraction identity before retrieval.",
        when_to_use=["The attraction name is ambiguous."],
        tool_priority=["baidu_place_search_mcp"],
        satisfies_needs=["entity_resolution"],
    ),
}

ORCHESTRATOR_SUBAGENT_NAMES = list(S5_SUBAGENT_PROFILES)


def subagent_definitions_for_prompt() -> list[dict]:
    return [
        {
            "name": profile.name,
            "summary": profile.summary,
            "when_to_use": profile.when_to_use,
            "satisfies_needs": profile.satisfies_needs,
            "tool_priority": profile.tool_priority,
            "delegatable_subagents": profile.delegatable_subagents,
        }
        for profile in S5_SUBAGENT_PROFILES.values()
    ]
