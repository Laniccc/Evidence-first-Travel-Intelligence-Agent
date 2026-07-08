"""S5 live_status task catalog — weather / traffic realtime."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

LIVE_STATUS_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "baidu_weather_mcp": AgentToolDefinition(
        name="baidu_weather_mcp",
        summary="百度天气：实时与短期预报。",
        when_to_use=["今日/明日天气", "出行当日天气风险"],
        satisfies_needs=["weather_today", "forecast", "weather"],
        call_order_hint="live_status 首选",
    ),
    "weather_context_agent": AgentToolDefinition(
        name="weather_context_agent",
        summary="S5 子代理：天气/气候 MCP 编排。",
        when_to_use=["需多源天气或坐标补全后查天气"],
        satisfies_needs=["forecast", "weather", "weather_today"],
    ),
    "baidu_traffic_mcp": AgentToolDefinition(
        name="baidu_traffic_mcp",
        summary="实时路况。",
        when_to_use=["当前拥堵、封路、自驾风险"],
        satisfies_needs=["traffic_status", "congestion_risk"],
    ),
}
