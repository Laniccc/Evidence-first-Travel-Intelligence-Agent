"""S5 ticket_price_lookup task catalog."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

TICKET_PRICE_LOOKUP_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "fact_lookup_agent": AgentToolDefinition(
        name="fact_lookup_agent",
        summary="S5 subagent for ticket price lookup phases and source families.",
        when_to_use=[
            "ticket_price facts such as entrance tickets, scenic shuttle tickets, or bundled products",
            "call with one lookup_phase and one source_family per turn",
            "prefer official_ticket_page_discovery before platform_ticket_candidate",
        ],
        when_not_to_use=[
            "nearby recommendation",
            "route planning",
            "generic review sentiment",
        ],
        parameters={
            "lookup_phase": "official_site_discovery|official_ticket_page_discovery|platform_ticket_candidate|ticket_price_extraction",
            "source_family": "official_operator|government_tourism|ticket_platform|web_reference",
            "claim_target": "ticket_price",
            "query_objectives": "LookupQueryObjective[]; omit only when using deterministic defaults",
        },
        satisfies_needs=["ticket_price", "entrance_ticket_price"],
        call_order_hint="ticket_price_lookup: official source -> official ticket page -> ticket platform candidate -> extraction/audit",
    ),
    "official_source_discovery_mcp": AgentToolDefinition(
        name="official_source_discovery_mcp",
        summary="Find official/operator/government candidates for ticket price verification.",
        when_to_use=[
            "first pass for ticket_price when no official URL is known",
            "classify search results before reading page content",
        ],
        prerequisites=["place_name and ticket_price claim target"],
        satisfies_needs=["ticket_price"],
        call_order_hint="Run before official_page_reader_mcp unless a known official URL is already present.",
    ),
    "official_page_reader_mcp": AgentToolDefinition(
        name="official_page_reader_mcp",
        summary="Read official page content and extract ticket price claims.",
        when_to_use=[
            "official_source_discovery_mcp or search_mcp produced readable URLs",
            "need current official ticket policy or pricing text",
        ],
        when_not_to_use=["no readable URL or prior search evidence"],
        prerequisites=["prior_evidence with readable URLs"],
        satisfies_needs=["ticket_price", "entrance_ticket_price"],
        call_order_hint="Use after official discovery/search results.",
    ),
    "browser_mcp": AgentToolDefinition(
        name="browser_mcp",
        summary="Fetch/read ticket pages that need browser-like page extraction.",
        when_to_use=["official_page_reader_mcp cannot extract enough page text"],
        prerequisites=["readable URL or prior search evidence"],
        satisfies_needs=["ticket_price"],
    ),
    "search_mcp": AgentToolDefinition(
        name="search_mcp",
        summary="Search web for official ticket page and platform ticket candidates.",
        when_to_use=[
            "official URL unknown",
            "gap-fill needs more ticket_price candidates",
            "build inputs for official_source_discovery_mcp",
        ],
        parameters={
            "query": "place + ticket keywords",
            "information_need": "ticket_price",
            "claim_target": "ticket_price",
        },
        satisfies_needs=["ticket_price"],
        call_order_hint="Use official/operator queries first; use OTA/platform queries as candidates only.",
    ),
    "fliggy_ticket_api_mcp": AgentToolDefinition(
        name="fliggy_ticket_api_mcp",
        summary="Ticket platform candidate for Fliggy price snapshots.",
        when_to_use=["official source not sufficient and ticket_platform phase is active"],
        when_not_to_use=["as official final proof"],
        satisfies_needs=["ticket_price_candidate"],
        call_order_hint="ticket_platform phase only; mark as third-party candidate.",
    ),
    "fliggy_ticket_snapshot_crawler_mcp": AgentToolDefinition(
        name="fliggy_ticket_snapshot_crawler_mcp",
        summary="Fallback Fliggy snapshot crawler for ticket candidates.",
        when_to_use=["fliggy_ticket_api_mcp unavailable or zero evidence"],
        when_not_to_use=["as official final proof"],
        satisfies_needs=["ticket_price_candidate"],
    ),
    "ticketlens_experience_mcp": AgentToolDefinition(
        name="ticketlens_experience_mcp",
        summary="TicketLens-style platform candidate for ticket price corroboration.",
        when_to_use=["ticket_platform phase needs another platform signal"],
        when_not_to_use=["as official final proof"],
        satisfies_needs=["ticket_price_candidate"],
    ),
    "ctrip_ticket_signal_crawler_mcp": AgentToolDefinition(
        name="ctrip_ticket_signal_crawler_mcp",
        summary="Ctrip ticket/search signal candidate.",
        when_to_use=["ticket platform candidate phase"],
        when_not_to_use=["as official final proof"],
        satisfies_needs=["ticket_price_candidate"],
    ),
    "dianping_ticket_signal_crawler_mcp": AgentToolDefinition(
        name="dianping_ticket_signal_crawler_mcp",
        summary="Dianping ticket/search signal candidate.",
        when_to_use=["ticket platform candidate phase"],
        when_not_to_use=["as official final proof"],
        satisfies_needs=["ticket_price_candidate"],
    ),
    "baidu_place_detail_mcp": AgentToolDefinition(
        name="baidu_place_detail_mcp",
        summary="Baidu POI detail candidate for address/UID and occasional ticket/opening hints.",
        when_to_use=["POI already resolved and ticket platform phase needs map candidate context"],
        when_not_to_use=["as official final ticket price proof"],
        satisfies_needs=["address_lookup", "ticket_price_candidate"],
    ),
    "ticket_price_history_query": AgentToolDefinition(
        name="ticket_price_history_query",
        summary="Local ticket snapshot history lookup.",
        when_to_use=["before repeating live platform crawlers"],
        satisfies_needs=["ticket_price_candidate"],
    ),
    "ticket_snapshot_store": AgentToolDefinition(
        name="ticket_snapshot_store",
        summary="Store or retrieve ticket platform snapshots.",
        when_to_use=["after platform candidate retrieval"],
        satisfies_needs=["ticket_price_candidate"],
    ),
}
