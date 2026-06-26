"""S5 review_first task catalog — reputation / value-for-money."""

from __future__ import annotations

from app.orchestrator.s5_task_tool_catalogs.types import AgentToolDefinition

REVIEW_FIRST_TOOL_CATALOG: dict[str, AgentToolDefinition] = {
    "dianping_review_crawler_mcp": AgentToolDefinition(
        name="dianping_review_crawler_mcp",
        summary="大众点评评价与评分：口碑核实、避雷。",
        when_to_use=[
            "用户关心评价、口碑、是否值得去",
            "对比多家店铺/景区体验",
        ],
        when_not_to_use=["门票价格硬事实", "路线距离"],
        satisfies_needs=["review_summary", "rating_candidate", "value_for_money", "reputation"],
        call_order_hint="review_first 任务可优先尝试",
    ),
    "fact_search_agent": AgentToolDefinition(
        name="fact_search_agent",
        summary="S5 子代理：游记/攻略类评价线索补证。",
        when_to_use=["平台爬虫不可用或需更多上下文"],
        satisfies_needs=["review_summary", "reputation", "value_for_money"],
    ),
    "search_mcp": AgentToolDefinition(
        name="search_mcp",
        summary="公开网页检索游记与评价线索。",
        when_to_use=["需要发现评价类 URL 或游记摘要"],
        satisfies_needs=["review_summary", "public_web_search"],
    ),
}
