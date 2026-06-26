"""S5 strict_fact_lookup task catalog — tickets, hours, hard facts."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

STRICT_FACT_LOOKUP_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "fact_lookup_agent": AgentToolDefinition(
        name="fact_lookup_agent",
        summary="S5 子代理：硬事实官方优先流水线（LOOKUP 任务首选）。",
        when_to_use=[
            "门票多少钱、开放时间、预约政策",
            "strict_fact_lookup 任务第一步",
        ],
        when_not_to_use=["周边美食列表", "路线距离", "天气"],
        parameters={
            "lookup_intent": "证据目标",
            "claim_target": "ticket_price|opening_hours|…",
            "search_query": "景区名",
        },
        satisfies_needs=["ticket_price", "opening_hours", "reservation_policy", "elevation"],
        call_order_hint="LOOKUP：先本代理，再 contradiction_decomposer",
    ),
    "official_source_discovery_mcp": AgentToolDefinition(
        name="official_source_discovery_mcp",
        summary="识别政府/景区/票务官方来源候选。",
        when_to_use=["opening_hours、ticket_price、seasonal_operation_status", "search_mcp 之后"],
        when_not_to_use=["周边推荐、路线距离"],
        prerequisites=["search_mcp 或已有 URL 线索"],
        satisfies_needs=["opening_hours", "ticket_price", "seasonal_operation_status"],
        call_order_hint="硬事实任务：search → official_discovery → official_reader",
    ),
    "official_page_reader_mcp": AgentToolDefinition(
        name="official_page_reader_mcp",
        summary="读取官方页正文提取开放时间/票价。",
        when_to_use=["需核实官网开放时间、票价、预约政策"],
        when_not_to_use=["路线规划"],
        prerequisites=["official_source_discovery_mcp 或 search_mcp 提供 URL"],
        satisfies_needs=["opening_hours", "ticket_price", "reservation_policy"],
    ),
    "fact_search_agent": AgentToolDefinition(
        name="fact_search_agent",
        summary="S5 子代理：网页/官方/票务硬事实检索。",
        when_to_use=["门票、开放时间、海拔、季节运营状态"],
        parameters={
            "lookup_intent": "证据目标描述",
            "claim_target": "claim 类型",
        },
        satisfies_needs=["ticket_price", "opening_hours", "elevation", "general_fact"],
        call_order_hint="strict_fact_lookup 主控子代理",
    ),
    "baidu_place_detail_mcp": AgentToolDefinition(
        name="baidu_place_detail_mcp",
        summary="百度 POI 详情：营业时间/地址候选（非官方终证）。",
        when_to_use=["官方页不可用时的营业时间候选"],
        when_not_to_use=["票价终证——优先官方页"],
        satisfies_needs=["opening_hours_candidate", "address_lookup"],
    ),
}
