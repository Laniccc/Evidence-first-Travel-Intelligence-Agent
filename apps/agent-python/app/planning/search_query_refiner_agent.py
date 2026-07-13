"""LLM follow-up search tasks when initial S5 keyword searches miss."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from app.planning.search_task_planner_agent import SearchTaskPlannerAgent
from app.planning.search_task import SearchTask

logger = logging.getLogger(__name__)


def _llm_client_class():
    return importlib.import_module("app.integrations.llm").LLMClient


class SearchQueryRefinerAgent:
    """LLM-only refinement 鈥?returns additional SearchTask objects."""

    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm = llm_client or _llm_client_class()()

    async def propose_tasks(self, state: Any) -> list[SearchTask]:
        planner = SearchTaskPlannerAgent(self.llm)
        return await planner.run(state, refine=True)

    async def propose(self, state: Any, seed_queries: list[str]) -> list[str]:
        """Legacy helper: return search_query strings from refined tasks."""
        _ = seed_queries
        tasks = await self.propose_tasks(state)
        return [t.search_query for t in tasks]
