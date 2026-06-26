"""S5 route_first task catalog — distance / duration / feasibility."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

ROUTE_FIRST_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "baidu_route_mcp": AgentToolDefinition(
        name="baidu_route_mcp",
        summary="百度地图路线：驾车/步行/公交距离与时长。",
        when_to_use=[
            "一日游是否够用、往返是否来得及",
            "城际/景区间真实公里数与驾车时长",
            "问题含「多远」「多久」「怎么去」",
        ],
        when_not_to_use=["仅景区内步行强度", "仅门票/开放时间"],
        prerequisites=["建议先 baidu_place_search_mcp 解析 destination"],
        satisfies_needs=["route_plan", "distance", "duration", "itinerary_feasibility"],
        call_order_hint="route_first 任务核心工具",
    ),
    "baidu_place_search_mcp": AgentToolDefinition(
        name="baidu_place_search_mcp",
        summary="百度 POI 检索：路线规划前解析目的地。",
        when_to_use=["destination 未解析为 POI", "需城市/区县消歧"],
        satisfies_needs=["entity_resolution", "place_lookup", "geo_resolution"],
        call_order_hint="通常在 baidu_route_mcp 之前",
    ),
    "route_feasibility_agent": AgentToolDefinition(
        name="route_feasibility_agent",
        summary="S5 子代理：距离/时长/路况一站式检索。",
        when_to_use=["一日游够玩吗", "多远多久", "自驾路况"],
        satisfies_needs=["route_plan", "distance", "duration", "itinerary_feasibility"],
        call_order_hint="route_first 可直接委托本子代理",
    ),
    "baidu_traffic_mcp": AgentToolDefinition(
        name="baidu_traffic_mcp",
        summary="路况与封路风险。",
        when_to_use=["自驾路线风险", "已有道路名或路线"],
        prerequisites=["建议已有路线或起终点"],
        satisfies_needs=["traffic_status", "congestion_risk"],
    ),
}
