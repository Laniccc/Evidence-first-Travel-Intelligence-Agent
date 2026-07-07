"""Resolve research queries to Agent Core contracts."""

from __future__ import annotations

from app.agent_core.contracts.base import BaseTaskContract, TaskContract
from app.agent_core.contracts.research import GeneralResearchContract, TechSurveyContract


_CONTRACTS: dict[str, TaskContract] = {
    "general_research": GeneralResearchContract(),
    "tech_survey": TechSurveyContract(),
    "competitor_analysis": GeneralResearchContract(),  # reuses general contract for now
    "general_lookup": BaseTaskContract(),
}


_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "tech_survey": [
        "技术趋势", "技术选型", "技术栈", "框架对比", "架构",
        "AI", "大模型", "LLM", "机器学习", "深度学习",
        "technology", "framework", "architecture", "tech stack",
    ],
    "competitor_analysis": [
        "竞品", "竞争对手", "市场分析", "市场份额", "对比",
        "competitor", "market analysis", "comparison",
    ],
}


def contract_for_task(task_class: str) -> TaskContract:
    return _CONTRACTS.get(task_class, _CONTRACTS["general_lookup"])


def task_class_for_query(query: str) -> str:
    """Classify a research query into a task class based on keyword matching."""
    for task_class, keywords in _TOPIC_KEYWORDS.items():
        if any(k in query for k in keywords):
            return task_class
    return "general_research"
