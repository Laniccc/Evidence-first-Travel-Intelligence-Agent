"""S5 sub-agent: plan multiple keyword search tasks from ResponseContract."""

from __future__ import annotations

import json
import logging
import re
import uuid

from app.llm_client import LLMClient
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)

_CORE_TERMS = re.compile(r"开放|通车|封路|门票|票价|开放时间|人流|天气", re.I)


class SearchTaskPlannerAgent:
    """Decompose evidence gathering into keyword-anchored search tasks for A2A dispatch."""

    def __init__(self, llm_client=None) -> None:
        self.llm = llm_client or LLMClient()

    async def run(self, state: TravelAgentState) -> list[SearchTask]:
        tasks = self._deterministic_tasks(state)
        if self.llm._should_use_anthropic():
            try:
                extra = await self._llm_expand_tasks(state, tasks)
                tasks.extend(extra)
            except Exception as exc:
                logger.warning("SearchTaskPlannerAgent LLM expand failed: %s", exc)
        return self._dedupe_tasks(tasks)

    def _deterministic_tasks(self, state: TravelAgentState) -> list[SearchTask]:
        need = ClaimSearchPlanner.primary_information_need(state) or "unknown"
        queries = ClaimSearchPlanner.build_queries(state)
        extras = ClaimSearchPlanner.refine_queries_after_misses(state, set(queries))
        merged = ClaimSearchPlanner._dedupe([*queries, *extras])
        max_tasks = ClaimSearchPlanner.max_search_attempts(state)

        tasks: list[SearchTask] = []
        for idx, query in enumerate(merged[:max_tasks]):
            anchors = self._anchors_for_query(state, query)
            tasks.append(
                SearchTask(
                    task_id=f"search-{idx + 1}",
                    anchor_keywords=anchors,
                    search_query=query,
                    information_need=need,
                    preferred_tool="search_mcp",
                    rationale="ClaimSearchPlanner seed task",
                )
            )
        return tasks

    async def _llm_expand_tasks(
        self,
        state: TravelAgentState,
        seed_tasks: list[SearchTask],
    ) -> list[SearchTask]:
        frame = state.semantic_frame
        place = frame.entities.places[0] if frame and frame.entities.places else None
        region = frame.entities.region if frame else None
        system = (
            "You plan keyword search tasks for a travel evidence agent (China).\n"
            "Return ONLY JSON: {\"tasks\":[{\"anchor_keywords\":[\"...\"],"
            "\"search_query\":\"...\",\"rationale\":\"...\",\"preferred_tool\":\"search_mcp\"}]}\n"
            "Rules:\n"
            "- Propose 1-3 NEW tasks not duplicating seed search_query values.\n"
            "- anchor_keywords: 2-4 strict tokens (place name, region, claim noun like 开放/通车).\n"
            "- search_query: short Baidu-friendly phrase that MUST contain at least one anchor.\n"
            "- You may add associative terms (G217, 交通运输厅, 公告) but keep anchors in query.\n"
            "- Do NOT answer the user; only plan searches."
        )
        user = json.dumps(
            {
                "raw_query": state.raw_user_query,
                "place": place,
                "region": region,
                "seed_tasks": [t.model_dump() for t in seed_tasks],
                "information_need": ClaimSearchPlanner.primary_information_need(state),
            },
            ensure_ascii=False,
        )
        raw = await self.llm.complete(system=system, user=user, max_tokens=500)
        data = json.loads(raw)
        bucket = data.get("tasks") if isinstance(data, dict) else []
        if not isinstance(bucket, list):
            return []

        need = ClaimSearchPlanner.primary_information_need(state) or "unknown"
        seed_queries = {t.search_query for t in seed_tasks}
        out: list[SearchTask] = []
        for item in bucket:
            if not isinstance(item, dict):
                continue
            query = str(item.get("search_query") or "").strip()
            if not query or query in seed_queries:
                continue
            anchors = item.get("anchor_keywords") or []
            if isinstance(anchors, str):
                anchors = [anchors]
            task = SearchTask(
                task_id=f"llm-{uuid.uuid4().hex[:8]}",
                anchor_keywords=[str(a).strip() for a in anchors if str(a).strip()],
                search_query=query,
                information_need=need,
                preferred_tool=str(item.get("preferred_tool") or "search_mcp"),
                rationale=str(item.get("rationale") or "LLM associative expansion"),
            )
            try:
                from app.agents.keyword_search_agent import KeywordSearchAgent

                KeywordSearchAgent.validate_task(task)
                out.append(task)
            except ValueError as exc:
                logger.debug("Skip invalid LLM search task: %s", exc)
        return out[:3]

    @staticmethod
    def _anchors_for_query(state: TravelAgentState, query: str) -> list[str]:
        frame = state.semantic_frame
        anchors: list[str] = []
        if frame and frame.entities.places:
            anchors.append(frame.entities.places[0])
        if frame and frame.entities.region:
            anchors.append(frame.entities.region)
        if frame and frame.entities.city:
            anchors.append(frame.entities.city)
        for term in _CORE_TERMS.findall(query):
            if term not in anchors:
                anchors.append(term)
        if not anchors:
            anchors.append(query[:8])
        return list(dict.fromkeys(a for a in anchors if a and str(a).strip()))

    @staticmethod
    def _dedupe_tasks(tasks: list[SearchTask]) -> list[SearchTask]:
        seen: set[str] = set()
        out: list[SearchTask] = []
        for task in tasks:
            key = task.search_query.strip()
            if key in seen:
                continue
            seen.add(key)
            out.append(task)
        return out
