"""S5 strict_fact_lookup task catalog — LookupResearchChain phases."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

STRICT_FACT_LOOKUP_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "fact_lookup_agent": AgentToolDefinition(
        name="fact_lookup_agent",
        summary="S5 子代理：按 lookup_phase + source_family 执行单轮检索（LOOKUP chain）。",
        when_to_use=[
            "official_discovery 或 fact_acquisition 阶段",
            "每次调用仅一个 source_family",
        ],
        when_not_to_use=["entity_anchor（用 entity_resolution_agent）", "周边美食", "路线"],
        parameters={
            "lookup_phase": "official_discovery|fact_acquisition",
            "source_family": "official_operator|government_tourism|ticket_platform|geo_authority|web_reference",
            "claim_target": "ticket_price|opening_hours|elevation|…",
            "query_objectives": "LookupQueryObjective[]",
        },
        satisfies_needs=["ticket_price", "opening_hours", "reservation_policy", "elevation"],
        call_order_hint="LOOKUP：entity_anchor → official_discovery → fact_acquisition → retrieval_audit",
    ),
    "entity_resolution_agent": AgentToolDefinition(
        name="entity_resolution_agent",
        summary="锚定景区/POI，消歧同名地点（LOOKUP entity_anchor 阶段）。",
        when_to_use=["LOOKUP 且地点未锚定", "同名行政区 vs 景区"],
        when_not_to_use=["已 fact_anchor 或 city+候选齐全"],
        satisfies_needs=["entity_resolution"],
        call_order_hint="LOOKUP chain L1：在 fact_lookup 之前",
    ),
    "official_source_discovery_mcp": AgentToolDefinition(
        name="official_source_discovery_mcp",
        summary="识别政府/景区/票务官方来源候选。",
        when_to_use=["opening_hours、ticket_price、seasonal_operation_status", "search_mcp 之后"],
        when_not_to_use=["周边推荐、路线距离"],
        prerequisites=["search_mcp 或已有 URL 线索"],
        satisfies_needs=["opening_hours", "ticket_price", "seasonal_operation_status"],
        call_order_hint="official_discovery phase 内由 fact_lookup_agent 调度",
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
        summary="S5 子代理：缺口/补充网页检索（audit 建议 continue 时）。",
        when_to_use=["LOOKUP audit 建议继续且 fact_lookup 阶段已尝试"],
        parameters={
            "lookup_intent": "证据目标描述",
            "claim_target": "claim 类型",
        },
        satisfies_needs=["ticket_price", "opening_hours", "elevation", "general_fact"],
        call_order_hint="LOOKUP：fact_lookup 多轮之后；gap-fill 定向 objective",
    ),
    "evidence_contradiction_decomposer_agent": AgentToolDefinition(
        name="evidence_contradiction_decomposer_agent",
        summary="拆分官方/平台/攻略等多层证据冲突。",
        when_to_use=["LOOKUP 出现票价/海拔口径冲突"],
        when_not_to_use=["尚无候选证据"],
        call_order_hint="LOOKUP：fact_acquisition 之后若 conflict_possible",
    ),
    "baidu_place_detail_mcp": AgentToolDefinition(
        name="baidu_place_detail_mcp",
        summary="百度 POI 详情：营业时间/地址候选（非官方终证）。",
        when_to_use=["map_candidate source_family"],
        when_not_to_use=["票价终证——优先官方页"],
        satisfies_needs=["opening_hours_candidate", "address_lookup"],
    ),
}
