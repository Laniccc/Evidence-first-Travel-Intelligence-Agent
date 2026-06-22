"""LLM/deterministic follow-up search queries when initial S5 searches miss."""

from __future__ import annotations

import json
import logging

from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)


class SearchQueryRefinerAgent:
    """Propose additional search queries from failed attempts (A2A helper for S5)."""

    def __init__(self, llm_client=None) -> None:
        from app.llm_client import LLMClient

        self.llm = llm_client or LLMClient()

    async def propose(self, state: TravelAgentState, seed_queries: list[str]) -> list[str]:
        tried = self._tried_queries(state)
        deterministic = ClaimSearchPlanner.refine_queries_after_misses(state, tried)
        extras: list[str] = list(deterministic)

        if self.llm._should_use_anthropic():
            try:
                llm_queries = await self._llm_propose(state, seed_queries, tried)
                extras.extend(llm_queries)
            except Exception as exc:
                logger.warning("SearchQueryRefinerAgent LLM failed: %s", exc)

        return list(dict.fromkeys(q for q in extras if q.strip() and q not in tried))

    async def _llm_propose(
        self,
        state: TravelAgentState,
        seed_queries: list[str],
        tried: set[str],
    ) -> list[str]:
        frame = state.semantic_frame
        system = (
            "You help refine web search queries for a travel evidence agent in China.\n"
            "Return ONLY JSON: {\"queries\": [\"...\", \"...\"]}\n"
            "Rules:\n"
            "- Propose 2-4 NEW queries not in tried_queries.\n"
            "- Prefer short Baidu-friendly phrases (6-20 chars) AND one official-source angle.\n"
            "- For road opening questions: include 通车/开放/公告/交通运输厅 when relevant.\n"
            "- Do NOT answer the user question; only suggest search strings."
        )
        user = json.dumps(
            {
                "raw_query": state.raw_user_query,
                "place": frame.entities.places[0] if frame and frame.entities.places else None,
                "region": frame.entities.region if frame else None,
                "seed_queries": seed_queries,
                "tried_queries": sorted(tried),
                "failed_snippets": self._failed_snippets(state),
            },
            ensure_ascii=False,
        )
        raw = await self.llm.complete(system=system, user=user, max_tokens=300)
        data = json.loads(raw)
        queries = data.get("queries") if isinstance(data, dict) else []
        if not isinstance(queries, list):
            return []
        return [str(q).strip() for q in queries if str(q).strip()]

    @staticmethod
    def _tried_queries(state: TravelAgentState) -> set[str]:
        tried: set[str] = set()
        for trace in state.tool_traces:
            if trace.tool_name != "search_mcp":
                continue
            q = (trace.input or {}).get("query")
            if q:
                tried.add(str(q).strip())
        return tried

    @staticmethod
    def _failed_snippets(state: TravelAgentState) -> list[str]:
        snippets: list[str] = []
        for ev in state.evidence:
            for claim in ev.claims:
                value = str(claim.value)
                if "No search hits" in value or "无结果" in value:
                    snippets.append(value[:120])
        return snippets[:6]
