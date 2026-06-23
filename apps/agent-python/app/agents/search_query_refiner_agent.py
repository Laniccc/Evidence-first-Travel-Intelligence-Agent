"""LLM follow-up search tasks when initial S5 keyword searches miss."""

from __future__ import annotations

import json
import logging

from app.agents.search_task_planner_agent import SearchTaskPlannerAgent, _extract_json
from app.llm_client import LLMClient
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)


class SearchQueryRefinerAgent:
    """LLM-only refinement — returns additional SearchTask objects."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or LLMClient()

    async def propose_tasks(self, state: TravelAgentState) -> list[SearchTask]:
        planner = SearchTaskPlannerAgent(self.llm)
        return await planner.run(state, refine=True)

    async def propose(self, state: TravelAgentState, seed_queries: list[str]) -> list[str]:
        """Legacy helper: return search_query strings from refined tasks."""
        _ = seed_queries
        tasks = await self.propose_tasks(state)
        return [t.search_query for t in tasks]
