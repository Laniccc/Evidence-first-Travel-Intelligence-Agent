"""S5 functional sub-agents: shared whitelist, per-agent MCP tool priority."""

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


S5_SUBAGENT_PROFILES: dict[str, S5SubagentProfile] = {
    "nearby_anchor_strategy_agent": S5SubagentProfile(
        name="nearby_anchor_strategy_agent",
        summary="判断周边检索锚点：精确门点 / 模糊区域 / 按消歧候选逐点检索。",
        when_to_use=[
            "nearby_food / nearby_poi 等需先确定百度检索中心",
            "同景区多 POI（各门/停车场）消歧",
            "用户说「附近」但未指明具体门点",
        ],
        tool_priority=[],
        satisfies_needs=[
            "nearby_food",
            "nearby_poi",
            "nearby_hotel",
            "restaurant_recommendation",
        ],
        delegatable_subagents=["entity_resolution_agent", "fact_search_agent"],
    ),
    "fact_lookup_agent": S5SubagentProfile(
        name="fact_lookup_agent",
        summary="硬事实检索：锚定景区 → 官方来源发现 → 读官方页 → 票务信号。",
        when_to_use=[
            "门票价格、开放时间、预约政策、海拔等 requires_exact_fact",
            "LOOKUP / strict_fact_lookup 任务类首选",
        ],
        tool_priority=[
            "baidu_place_search_mcp",
            "baidu_geocode_mcp",
            "wikidata_mcp",
            "wikipedia_mcp",
            "osm_mcp",
            "search_mcp",
            "official_source_discovery_mcp",
            "official_page_reader_mcp",
            "ctrip_ticket_signal_crawler_mcp",
            "dianping_ticket_signal_crawler_mcp",
            "baidu_place_detail_mcp",
        ],
        satisfies_needs=[
            "ticket_price",
            "opening_hours",
            "reservation_policy",
            "seasonal_operation_status",
            "elevation",
            "general_fact",
        ],
    ),
    "entity_resolution_agent": S5SubagentProfile(
        name="entity_resolution_agent",
        summary="锚定地点/POI/行政区：同名消歧、坐标、uid。",
        when_to_use=[
            "用户地点未解析或缺 city/region",
            "evidence 含 place_candidates 多地同名",
            "路线/天气/详情前需确认 POI",
            "nearby 问题：消歧后按候选逐点做周边检索",
        ],
        tool_priority=[
            "baidu_place_search_mcp",
            "baidu_geocode_mcp",
            "baidu_reverse_geocode_mcp",
            "baidu_place_detail_mcp",
            "osm_mcp",
            "places_mcp",
        ],
        satisfies_needs=[
            "entity_resolution",
            "geo_resolution",
            "place_lookup",
            "place_candidates",
            "nearby_food",
            "nearby_poi",
        ],
        delegatable_subagents=[
            "nearby_anchor_strategy_agent",
            "fact_search_agent",
        ],
    ),
    "route_feasibility_agent": S5SubagentProfile(
        name="route_feasibility_agent",
        summary="城际/景区路线、距离时长、路况与多点多方案。",
        when_to_use=[
            "一日游够玩吗、多远多久、怎么去",
            "需要结构化 distance/duration",
            "独库公路等路况",
        ],
        tool_priority=[
            "baidu_place_search_mcp",
            "baidu_route_mcp",
            "baidu_route_matrix_mcp",
            "baidu_traffic_mcp",
        ],
        satisfies_needs=[
            "route_plan",
            "distance",
            "duration",
            "transport_planning",
            "itinerary_feasibility",
            "transit",
            "traffic_status",
        ],
    ),
    "fact_search_agent": S5SubagentProfile(
        name="fact_search_agent",
        summary="网页/官方页/票务爬虫检索硬事实与攻略线索。",
        when_to_use=[
            "门票、开放时间、海拔、季节建议",
            "需要 open-webSearch 或官方页核实",
            "实体已锚定后的 claim 补证",
        ],
        tool_priority=[
            "search_mcp",
            "ctrip_review_crawler_mcp",
            "baidu_place_search_mcp",
            "baidu_place_detail_mcp",
            "dianping_nearby_crawler_mcp",
            "dianping_review_crawler_mcp",
            "official_source_discovery_mcp",
            "official_page_reader_mcp",
            "browser_mcp",
            "wikipedia_mcp",
            "wikidata_mcp",
            "ctrip_ticket_signal_crawler_mcp",
            "dianping_ticket_signal_crawler_mcp",
        ],
        satisfies_needs=[
            "ticket_price",
            "opening_hours",
            "elevation",
            "general_fact",
            "seasonality",
            "best_time_to_visit",
            "reviews",
            "crowd_level",
            "nearby_food",
            "nearby_poi",
            "restaurant_recommendation",
            "review_summary",
            "reputation",
        ],
        delegatable_subagents=[
            "nearby_anchor_strategy_agent",
            "entity_resolution_agent",
        ],
    ),
    "weather_context_agent": S5SubagentProfile(
        name="weather_context_agent",
        summary="短期天气与气候（需坐标或城市）。",
        when_to_use=["今日/明日天气", "出行前短期气象"],
        tool_priority=[
            "baidu_weather_mcp",
            "openmeteo_mcp",
            "weather_mcp",
            "climate_mcp",
        ],
        satisfies_needs=["forecast", "weather", "weather_today", "today_weather"],
    ),
    "evidence_contradiction_decomposer_agent": S5SubagentProfile(
        name="evidence_contradiction_decomposer_agent",
        summary="多源口径分歧分解（票种/距离范围/时长范围）。",
        when_to_use=["同一 claim 多值冲突", "需分 tier 呈现"],
        tool_priority=[],
        satisfies_needs=["contradiction_resolution"],
    ),
}

ORCHESTRATOR_SUBAGENT_NAMES = list(S5_SUBAGENT_PROFILES.keys())


def subagent_definitions_for_prompt() -> list[dict]:
    return [
        {
            "name": p.name,
            "summary": p.summary,
            "when_to_use": p.when_to_use,
            "satisfies_needs": p.satisfies_needs,
            "tool_priority": p.tool_priority[:8],
            "delegatable_subagents": list(p.delegatable_subagents)[:6],
        }
        for p in S5_SUBAGENT_PROFILES.values()
    ]
