"""S5 minimal_probe task catalog — entity resolution / geo anchor."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

MINIMAL_PROBE_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "baidu_place_search_mcp": AgentToolDefinition(
        name="baidu_place_search_mcp",
        summary="百度地图 POI 检索：消歧与锚定（非周边推荐主路径）。",
        when_to_use=[
            "地点消歧（同名景区）",
            "解析景区正式名称、行政区、uid",
            "路线规划前确认目的地 POI",
        ],
        when_not_to_use=["用户问周边美食/酒店列表——转入 poi_recommendation 任务"],
        parameters={
            "place_name": "景区/地点名",
            "city": "城市",
            "region": "行政区（消歧）",
            "country": "China",
        },
        satisfies_needs=["entity_resolution", "place_lookup", "geo_resolution", "place_candidates"],
        call_order_hint="实体解析任务首选 MCP",
    ),
    "baidu_geocode_mcp": AgentToolDefinition(
        name="baidu_geocode_mcp",
        summary="地址/地名 → 经纬度（锚点补全）。",
        when_to_use=["POI 检索后仍缺坐标", "天气/路线工具需要坐标"],
        parameters={"address": "地址或地名", "place_name": "地点"},
        satisfies_needs=["geocode", "coordinates", "geo_resolution"],
    ),
    "entity_resolution_agent": AgentToolDefinition(
        name="entity_resolution_agent",
        summary="S5 子代理：地点/POI 锚定与同名消歧。",
        when_to_use=["地点未解析", "place_candidates 歧义"],
        parameters={
            "lookup_intent": "锚定意图",
            "search_query": "地点名",
            "tool_parameters": "region/city 等",
        },
        satisfies_needs=["entity_resolution", "geo_resolution", "place_lookup"],
        call_order_hint="minimal_probe 任务可直接调用本子代理",
    ),
    "search_mcp": AgentToolDefinition(
        name="search_mcp",
        summary="网页检索辅助消歧（官方名、别名线索）。",
        when_to_use=["百度 POI 检索结果不足或同名过多"],
        when_not_to_use=["已有明确 POI uid"],
        parameters={"search_query": "地名+城市", "information_need": "entity_resolution"},
        satisfies_needs=["entity_resolution", "place_lookup"],
    ),
}
