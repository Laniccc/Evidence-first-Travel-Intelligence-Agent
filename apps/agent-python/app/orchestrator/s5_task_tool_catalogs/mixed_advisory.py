"""S5 mixed_advisory task catalog — blended advice (season, route, reviews)."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

MIXED_ADVISORY_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "search_mcp": AgentToolDefinition(
        name="search_mcp",
        summary="公开网页检索：攻略、季节、综合建议线索。",
        when_to_use=["开放建议类问题", "需多维度软信息"],
        satisfies_needs=["seasonality", "travel_advice", "review_summary"],
        call_order_hint="mixed_advisory 常用起点",
    ),
    "fact_search_agent": AgentToolDefinition(
        name="fact_search_agent",
        summary="S5 子代理：多 claim 补证编排。",
        when_to_use=["需同时补季节/评价/事实等多类证据"],
        satisfies_needs=["seasonality", "review_summary", "general_fact"],
    ),
    "baidu_route_mcp": AgentToolDefinition(
        name="baidu_route_mcp",
        summary="路线距离/时长（建议类问题若涉及交通可行性）。",
        when_to_use=["问题隐含「够玩吗」「来得及吗」"],
        when_not_to_use=["纯季节/评价无交通维度"],
        satisfies_needs=["distance", "duration", "itinerary_feasibility"],
    ),
}
