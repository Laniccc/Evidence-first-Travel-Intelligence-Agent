"""Claude agent-style tool definitions for LLM tool selection in S5."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentToolDefinition(BaseModel):
    """Rich tool card exposed to LLM controllers (when_to_use, params, prerequisites)."""

    name: str
    summary: str
    when_to_use: list[str] = Field(default_factory=list)
    when_not_to_use: list[str] = Field(default_factory=list)
    parameters: dict[str, str] = Field(default_factory=dict)
    prerequisites: list[str] = Field(default_factory=list)
    satisfies_needs: list[str] = Field(default_factory=list)
    call_order_hint: str = ""

    def to_prompt_dict(self) -> dict:
        return {
            "name": self.name,
            "summary": self.summary,
            "when_to_use": self.when_to_use,
            "when_not_to_use": self.when_not_to_use,
            "parameters": self.parameters,
            "prerequisites": self.prerequisites,
            "satisfies_needs": self.satisfies_needs,
            "call_order_hint": self.call_order_hint or None,
        }


AGENT_TOOL_SPECS: dict[str, AgentToolDefinition] = {
    "search_mcp": AgentToolDefinition(
        name="search_mcp",
        summary="公开网页检索（攻略、游记、季节、临时通知线索）。",
        when_to_use=[
            "需要发现官方页面、游记、通知类 URL 作为后续 browser/official 读取入口",
            "季节、攻略、评价类软信息，尚无结构化证据",
        ],
        when_not_to_use=[
            "已需要精确公里/驾车时长——应优先 baidu_route_mcp",
            "已有官方 URL 待读取——用 official_page_reader_mcp / browser_mcp",
        ],
        parameters={"search_query": "检索词（含地名锚点）", "information_need": "检索目的 claim 类型"},
        satisfies_needs=["public_web_search", "seasonality", "review_summary", "travel_advice"],
    ),
    "official_source_discovery_mcp": AgentToolDefinition(
        name="official_source_discovery_mcp",
        summary="从已有搜索结果中识别政府/景区/票务官方来源候选。",
        when_to_use=["opening_hours、ticket_price、seasonal_operation_status 等硬事实", "search_mcp 之后"],
        when_not_to_use=["仅需路线距离/时长"],
        parameters={"prior_evidence": "已有 search 证据", "claim_type": "目标 claim"},
        prerequisites=["search_mcp 或 keyword_search 已有 hits"],
        satisfies_needs=["opening_hours", "ticket_price", "seasonal_operation_status"],
        call_order_hint="通常在 search_mcp 之后、official_page_reader 之前",
    ),
    "official_page_reader_mcp": AgentToolDefinition(
        name="official_page_reader_mcp",
        summary="读取官方/政务/景区页面正文，提取开放时间与票价。",
        when_to_use=["需要核实官网上的开放时间、票价、预约政策"],
        when_not_to_use=["路线规划、两地距离"],
        parameters={"url": "官方页 URL（可选）", "place_name": "地点", "information_need": "opening_hours|ticket_price"},
        prerequisites=["official_source_discovery_mcp 或 search_mcp 提供 URL"],
        satisfies_needs=["opening_hours", "ticket_price", "reservation_policy"],
    ),
    "browser_mcp": AgentToolDefinition(
        name="browser_mcp",
        summary="动态网页抓取（非结构化官方页/公告）。",
        when_to_use=["official_page_reader 失败或需二次抓取公告页"],
        when_not_to_use=["两地驾车距离/时长"],
        satisfies_needs=["opening_hours", "temporary_closure", "travel_advice"],
    ),
    "baidu_place_search_mcp": AgentToolDefinition(
        name="baidu_place_search_mcp",
        summary="百度地图 POI 检索：解析景区正式名称、行政区、uid。",
        when_to_use=[
            "地点消歧（同名景区）",
            "路线规划前确认目的地 POI",
            "需要城市/区县上下文",
        ],
        when_not_to_use=["仅需要网页攻略文本"],
        parameters={"place_name": "景区/地点名", "city": "城市", "country": "China"},
        satisfies_needs=["entity_resolution", "place_lookup", "geo_resolution"],
        call_order_hint="调用 baidu_route_mcp 前建议先解析目的地 POI",
    ),
    "baidu_place_detail_mcp": AgentToolDefinition(
        name="baidu_place_detail_mcp",
        summary="百度地图 POI 详情（地址、评分、营业时间候选）。",
        when_to_use=["需要 POI 地址、候选营业时间、评分"],
        when_not_to_use=["跨省驾车距离——用 baidu_route_mcp"],
        parameters={"uid": "来自 baidu_place_search 的 POI uid", "place_name": "地点名"},
        prerequisites=["baidu_place_search_mcp 提供 uid"],
        satisfies_needs=["opening_hours_candidate", "address_lookup"],
    ),
    "baidu_geocode_mcp": AgentToolDefinition(
        name="baidu_geocode_mcp",
        summary="地址/地名 → 经纬度坐标。",
        when_to_use=["天气/路线工具需要坐标但 evidence 中尚无"],
        parameters={"address": "地址或地名", "place_name": "地点"},
        satisfies_needs=["geocode", "coordinates"],
    ),
    "baidu_route_mcp": AgentToolDefinition(
        name="baidu_route_mcp",
        summary="百度地图两点路线规划：驾车/步行/公交距离与预计时长（结构化）。",
        when_to_use=[
            "用户问一日游是否够用、往返是否来得及——必须先算路程+驾车时长",
            "需要乌鲁木齐/阿勒泰等城市到景区的真实公里数（勿仅用攻略摘要）",
            "对比两地交通方式或评估 itinerary_feasibility",
            "问题含「多远」「多久」「怎么去」「一天够吗」且涉及城际交通",
        ],
        when_not_to_use=[
            "仅问景区内步行强度、游玩时长（无城际交通）",
            "仅问门票价格或开放时间",
        ],
        parameters={
            "origin": "起点城市/地点（必填；新疆一日游默认可推 乌鲁木齐市）",
            "destination": "终点景区 POI 名（必填）",
            "mode": "driving|walking|transit，默认 driving",
            "place_name": "目的地景区名",
        },
        prerequisites=[
            "建议先 baidu_place_search_mcp 解析 destination",
            "origin/destination 必须同时提供",
        ],
        satisfies_needs=[
            "route_plan",
            "distance",
            "duration",
            "transport_planning",
            "itinerary_feasibility",
            "transit",
        ],
        call_order_hint="一日游/够玩吗类问题：在 search_mcp 之后、finish 之前必须尝试一次",
    ),
    "baidu_route_matrix_mcp": AgentToolDefinition(
        name="baidu_route_matrix_mcp",
        summary="百度地图多点距离/时间矩阵（多景点串联可行性）。",
        when_to_use=["多景点行程串联、比较多个目的地间车程", "comparison 模式两地交通对比"],
        when_not_to_use=["单点开放时间查询"],
        parameters={
            "origins": "起点列表",
            "destinations": "终点列表",
            "mode": "driving",
        },
        prerequisites=["baidu_place_search_mcp 解析各地点"],
        satisfies_needs=["route_plan", "itinerary_feasibility", "distance", "duration"],
    ),
    "baidu_traffic_mcp": AgentToolDefinition(
        name="baidu_traffic_mcp",
        summary="百度地图路况（拥堵、封路风险）。",
        when_to_use=["自驾路线风险、独库公路等路况", "已有路线或道路名"],
        when_not_to_use=["首次获取两地距离——先用 baidu_route_mcp"],
        parameters={"road_name": "道路名", "query": "路况查询词"},
        satisfies_needs=["traffic_status", "road_traffic", "congestion_risk"],
    ),
    "baidu_weather_mcp": AgentToolDefinition(
        name="baidu_weather_mcp",
        summary="百度地图天气（实时/短期预报）。",
        when_to_use=["今日天气、出行当日天气风险"],
        satisfies_needs=["weather_today", "forecast", "weather"],
    ),
    "keyword_search_agent": AgentToolDefinition(
        name="keyword_search_agent",
        summary="S5 子代理：按 lookup_intent 选 MCP 并 CALL_TOOL（第一方工具执行者）。",
        when_to_use=["search_task_planner 分解后的每条证据查询任务"],
        when_not_to_use=["未规划为 SearchTask 的一次性工具调用"],
        parameters={
            "lookup_intent": "S5 理解后需获取的证据描述（必填）",
            "claim_target": "目标 claim 类型",
            "tool_parameters": "结构化 MCP 参数（路线类含 origin/destination）",
            "preferred_tool": "工具提示；子代理结合 agent_tool_definitions 最终选择",
        },
        call_order_hint="读取 prompt_context.agent_tool_definitions 的 when_to_use / satisfies_needs",
    ),
    "search_task_planner_agent": AgentToolDefinition(
        name="search_task_planner_agent",
        summary="S5 子代理：将用户问题分解为 keyword_search 任务。",
        when_to_use=["S5 开始时规划检索词", "每 2 次 keyword_search 后 refine"],
        parameters={"refine": "true 表示基于已有 evidence 调整检索"},
    ),
}


def catalog_entry(tool_name: str) -> AgentToolDefinition | None:
    return AGENT_TOOL_SPECS.get(tool_name)


def enrich_descriptor_fields(tool_name: str, base_description: str) -> dict:
    """Merge static catalog into ToolDescriptor-compatible extra fields."""
    spec = catalog_entry(tool_name)
    if not spec:
        return {"description": base_description}
    desc = spec.summary
    if base_description and base_description not in desc:
        desc = f"{spec.summary} ({base_description})"
    return {
        "description": desc,
        "when_to_use": spec.when_to_use,
        "when_not_to_use": spec.when_not_to_use,
        "parameters_hint": "; ".join(f"{k}: {v}" for k, v in spec.parameters.items()),
        "prerequisites": spec.prerequisites,
        "satisfies_needs": spec.satisfies_needs,
        "call_order_hint": spec.call_order_hint,
    }


def agent_tool_definitions_for_allowed(allowed_names: list[str]) -> list[dict]:
    """LLM-facing tool cards for current whitelist only."""
    out: list[dict] = []
    for name in allowed_names:
        spec = catalog_entry(name)
        if spec:
            out.append(spec.to_prompt_dict())
        else:
            out.append({"name": name, "summary": name, "when_to_use": [], "parameters": {}})
    return out


def route_tools_priority() -> list[str]:
    return ["baidu_place_search_mcp", "baidu_route_mcp", "baidu_route_matrix_mcp", "baidu_traffic_mcp"]
