"""S5 poi_recommendation task tool catalog — nearby POI / dining discovery."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.shared import SHARED_TOOL_CATALOG
from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

POI_RECOMMENDATION_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "baidu_place_search_mcp": AgentToolDefinition(
        name="baidu_place_search_mcp",
        summary="百度地图 POI 检索与周边圆形检索（nearby 任务主检索面）。",
        when_to_use=[
            "用户问「XX附近有什么」——先定锚点再做圆形检索",
            "同景区多门点/停车场消歧后，按候选锚点分别检索",
            "需要按距离列出周边 POI 候选",
            "酒店/景点/休息区等非美食类 nearby",
        ],
        when_not_to_use=[
            "仅需要网页攻略文本",
            "城际路线距离/时长",
        ],
        parameters={
            "place_name": "景区/地点名",
            "city": "城市",
            "region": "行政区（消歧）",
            "tag": "POI 类型偏好，如美食/酒店/景点",
            "location": "圆形检索中心 lat,lng",
            "radius": "周边检索半径（米）",
            "anchor_location_key": "消歧候选 location_key（写入 evidence 归属）",
            "country": "China",
        },
        prerequisites=["建议先 entity_resolution_agent / nearby_anchor_strategy_agent 定锚点"],
        satisfies_needs=["nearby_food", "nearby_poi", "restaurant_recommendation", "geo_resolution"],
        call_order_hint="锚点策略 → 本工具；S8 片区合成会汇总全部 FOOD 证据",
    ),
    "baidu_place_detail_mcp": AgentToolDefinition(
        name="baidu_place_detail_mcp",
        summary="百度地图 POI 详情（地址、营业时间候选、百度侧评分）。",
        when_to_use=["已有 uid 需补地址/营业时间", "百度候选需核实基础字段"],
        when_not_to_use=["跨省驾车距离"],
        parameters={"uid": "来自 baidu_place_search_mcp", "place_name": "地点名"},
        prerequisites=["baidu_place_search_mcp 提供 uid"],
        satisfies_needs=["opening_hours_candidate", "address_lookup", "rating_candidate", "nearby_poi"],
    ),
    "dianping_nearby_crawler_mcp": AgentToolDefinition(
        name="dianping_nearby_crawler_mcp",
        summary="大众点评附近商户：评分、评论量、星级筛选。",
        when_to_use=[
            "美食/餐厅类 nearby 问题时可优先考虑（与百度并行或互补，由你判断）",
            "需要按口碑而非仅距离排序餐厅候选",
            "已确定检索锚点坐标",
        ],
        when_not_to_use=["无城市/地点锚点", "纯酒店/景点/停车场等非餐饮 nearby"],
        parameters={
            "place_name": "锚点景区或门点名称",
            "city": "城市",
            "query": "检索词（如 美食 餐厅）",
            "mode": "nearby_search",
            "sort_by": "rating_review_count",
        },
        prerequisites=["锚点已解析；可与 baidu_place_search 互补使用"],
        satisfies_needs=["nearby_food", "restaurant_recommendation", "rating_candidate", "review_summary"],
        call_order_hint="非强制；美食场景可优先尝试，非美食不必调用",
    ),
    "dianping_review_crawler_mcp": AgentToolDefinition(
        name="dianping_review_crawler_mcp",
        summary="大众点评店铺评价与评分：验证口碑、避雷。",
        when_to_use=[
            "美食 nearby 已有店名候选，需核实评分/评论摘要时可考虑",
            "对比多家餐厅口碑",
        ],
        when_not_to_use=["尚无任何餐厅候选", "非餐饮 nearby"],
        parameters={"place_name": "店名或景区", "city": "城市", "query": "店名+美食"},
        satisfies_needs=["review_summary", "rating_candidate", "value_for_money", "nearby_food"],
        call_order_hint="在已有店名后补抓评价；非美食场景通常不需要",
    ),
    "entity_resolution_agent": AgentToolDefinition(
        name="entity_resolution_agent",
        summary="S5 子代理：地点锚定与同名消歧（nearby 第一步）。",
        when_to_use=[
            "地点未解析或 place_candidates 歧义",
            "nearby 需为每个消歧候选分别检索周边",
        ],
        parameters={
            "lookup_intent": "锚定意图",
            "search_query": "地点名",
            "anchor_keywords": "地点 token",
            "tool_parameters": "region/city 等",
        },
        satisfies_needs=["entity_resolution", "geo_resolution", "place_lookup", "nearby_food", "nearby_poi"],
        call_order_hint="nearby 任务通常第一步；内部可委托 nearby_anchor_strategy_agent",
    ),
    "nearby_anchor_strategy_agent": AgentToolDefinition(
        name="nearby_anchor_strategy_agent",
        summary="S5 子代理：精确门点 / 模糊区域 / 逐候选检索策略。",
        when_to_use=[
            "用户问「XX附近有什么」且地点可能歧义",
            "需确定百度/第三方检索中心坐标与半径",
            "同景区多门点/停车场并存",
        ],
        when_not_to_use=["纯城际路线", "门票硬事实无地理锚点"],
        parameters={
            "nearby_claim": "nearby_food|nearby_poi|…",
            "candidates": "place_candidates 列表",
            "parent_subagent": "调用方子代理名",
        },
        satisfies_needs=["nearby_food", "nearby_poi", "restaurant_recommendation"],
        call_order_hint="在周边 MCP 检索之前；可由 entity_resolution_agent 递归委托",
    ),
    "call_subagent": AgentToolDefinition(
        name="call_subagent",
        summary="S5 子代理递归委托。",
        when_to_use=[
            "nearby 需先定锚点再检索",
            "实体解析后需专项 fact_search",
        ],
        parameters={
            "target_subagent": "nearby_anchor_strategy_agent|fact_search_agent|…",
            "arguments": "子代理 task 字段",
        },
        call_order_hint="entity_resolution → nearby_anchor_strategy → 按候选检索",
    ),
    "fact_search_agent": AgentToolDefinition(
        name="fact_search_agent",
        summary="S5 子代理：补证检索（攻略线索、软信息）。",
        when_to_use=["结构化 MCP 不足时需网页/攻略补证", "季节/评价类软信息"],
        parameters={
            "lookup_intent": "证据目标",
            "search_query": "检索词",
            "claim_target": "claim 类型",
        },
        satisfies_needs=["review_summary", "seasonality", "nearby_food", "nearby_poi"],
    ),
    "search_mcp": SHARED_TOOL_CATALOG["search_mcp"].model_copy(
        update={
            "when_to_use": SHARED_TOOL_CATALOG["search_mcp"].when_to_use
            + ["nearby 结构化证据不足时的游记/攻略线索"],
        }
    ),
}
