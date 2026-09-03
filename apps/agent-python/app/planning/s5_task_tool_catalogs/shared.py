"""Small compatibility catalog for evidence-backed fact acquisition."""

from __future__ import annotations

from app.planning.s5_task_tool_catalogs.types import AgentToolDefinition


SHARED_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "search_mcp": AgentToolDefinition(
        name="search_mcp",
        summary="Discover candidate public and official source pages.",
        when_to_use=["A managed fact is missing and a source URL must be discovered."],
        parameters={"search_query": "Attraction and fact-specific query."},
        satisfies_needs=["general_description", "visitor_notice", "opening_hours", "ticket_price"],
    ),
    "official_source_discovery_mcp": AgentToolDefinition(
        name="official_source_discovery_mcp",
        summary="Select an official attraction or government source from search results.",
        when_to_use=["A hard fact needs authoritative provenance."],
        prerequisites=["search results"],
        satisfies_needs=["opening_hours", "ticket_price", "visitor_notice"],
    ),
    "official_page_reader_mcp": AgentToolDefinition(
        name="official_page_reader_mcp",
        summary="Read an official page for a bounded attraction fact.",
        when_to_use=["An official source URL is available."],
        parameters={"url": "Official URL", "information_need": "Managed fact type"},
        satisfies_needs=["opening_hours", "ticket_price", "visitor_notice", "accessibility"],
    ),
    "browser_mcp": AgentToolDefinition(
        name="browser_mcp",
        summary="Fallback reader for dynamic official pages.",
        when_to_use=["The official page reader cannot extract the page."],
        satisfies_needs=["opening_hours", "visitor_notice"],
    ),
    "fact_search_agent": AgentToolDefinition(
        name="fact_search_agent",
        summary="Acquire one missing fact with source provenance.",
        when_to_use=["Hybrid retrieval exposes a hard evidence gap."],
        parameters={"claim_target": "Managed fact type"},
        satisfies_needs=["ticket_price", "opening_hours", "accessibility", "general_description"],
    ),
    "entity_resolution_agent": AgentToolDefinition(
        name="entity_resolution_agent",
        summary="Resolve an attraction identity before fact retrieval.",
        when_to_use=["The attraction name is ambiguous."],
        satisfies_needs=["entity_resolution"],
    ),
}
