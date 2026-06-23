"""S5 sub-agent: LLM plans keyword-anchored search tasks for A2A dispatch."""

from __future__ import annotations

import json
import logging
import uuid

from app.llm_client import LLMClient
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)

_SYSTEM_INITIAL = """You plan keyword search tasks for a travel evidence agent (China).
Return ONLY JSON:
{"tasks":[{"anchor_keywords":["..."],"search_query":"...","rationale":"...","preferred_tool":"search_mcp"}]}

Rules:
- Propose 2-5 search tasks tailored to the user's actual question and claim_types.
- anchor_keywords: 2-4 strict tokens (place name, city/region, and terms directly relevant to the user need).
- search_query: short Baidu-friendly phrase; MUST contain at least one anchor keyword.
- Derive keywords from raw_query and information needs — do NOT invent unrelated topics (e.g. no 通车/开放月份 unless the user asks about road opening or seasonal closure).
- Do NOT answer the user; only plan searches.
- Keep rationale under 40 Chinese characters; escape quotes inside strings."""

_SYSTEM_REFINE = """You refine keyword search tasks after prior searches returned no useful hits.
Return ONLY JSON with 1-3 NEW tasks (same schema as initial planning).
Rules:
- Do NOT repeat tried_search_queries.
- Stay aligned with raw_query and claim_types; propose shorter or alternative phrasing only.
- anchor_keywords must appear in search_query."""

_NEED_QUERY_HINTS: dict[str, str] = {
    "ticket_price": "门票价格",
    "opening_hours": "开放时间",
    "best_time_to_visit": "什么时候去",
    "seasonality": "最佳旅游季节",
    "seasonal_operation_status": "开放月份",
    "temporary_closure": "闭园通知",
    "reservation_policy": "预约政策",
    "elderly_suitability": "适合老人",
    "family_friendly": "适合带孩子",
    "value_for_money": "性价比",
    "review_summary": "游客评价",
    "crowd_level": "人流量",
    "current_crowd": "实时客流",
}


class SearchTaskPlannerAgent:
    """LLM-only decomposition into keyword_search_agent tasks."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or LLMClient()

    async def run(self, state: TravelAgentState, *, refine: bool = False) -> list[SearchTask]:
        ctx = ClaimSearchPlanner.planning_context(state)
        if refine:
            ctx["existing_tasks"] = (state.structured_result or {}).get("search_tasks") or []
        tasks = await self._llm_plan_tasks(ctx, refine=refine)
        return self._dedupe_tasks(tasks)

    async def _llm_plan_tasks(self, ctx: dict, *, refine: bool) -> list[SearchTask]:
        system = _SYSTEM_REFINE if refine else _SYSTEM_INITIAL
        max_tasks = int(ctx.get("max_tasks") or 3)
        if refine:
            max_tasks = min(3, max_tasks)
        user = json.dumps(ctx, ensure_ascii=False)
        raw = await self.llm.complete(system=system, user=user, max_tokens=1200)
        data = _parse_llm_tasks_payload(raw)
        if data is None:
            logger.warning(
                "SearchTaskPlannerAgent: invalid LLM JSON (len=%s); using rule-based fallback",
                len(raw or ""),
            )
            return self._fallback_plan_tasks(ctx, refine=refine, max_tasks=max_tasks)
        return self._tasks_from_payload(data, ctx, refine=refine, max_tasks=max_tasks)

    def _tasks_from_payload(
        self,
        data: dict,
        ctx: dict,
        *,
        refine: bool,
        max_tasks: int,
    ) -> list[SearchTask]:
        bucket = data.get("tasks") if isinstance(data, dict) else []
        if not isinstance(bucket, list):
            raise ValueError("LLM search planner returned invalid tasks payload")

        need = ctx.get("primary_information_need") or "unknown"
        tried = set(ctx.get("tried_search_queries") or [])
        out: list[SearchTask] = []
        for item in bucket:
            if not isinstance(item, dict):
                continue
            query = str(item.get("search_query") or "").strip()
            if not query or query in tried:
                continue
            anchors = item.get("anchor_keywords") or []
            if isinstance(anchors, str):
                anchors = [anchors]
            task = SearchTask(
                task_id=f"{'refine' if refine else 'search'}-{uuid.uuid4().hex[:8]}",
                anchor_keywords=[str(a).strip() for a in anchors if str(a).strip()],
                search_query=query,
                information_need=str(item.get("information_need") or need),
                preferred_tool=str(item.get("preferred_tool") or "search_mcp"),
                rationale=str(item.get("rationale") or ("LLM refine" if refine else "LLM planned")),
            )
            from app.agents.keyword_search_agent import KeywordSearchAgent

            try:
                KeywordSearchAgent.validate_task(task)
            except ValueError:
                continue
            out.append(task)
            if len(out) >= max_tasks:
                break

        if not out:
            return self._fallback_plan_tasks(ctx, refine=refine, max_tasks=max_tasks)
        return out

    def _fallback_plan_tasks(self, ctx: dict, *, refine: bool, max_tasks: int) -> list[SearchTask]:
        entities = ctx.get("entities") or {}
        places = [str(p).strip() for p in (entities.get("places") or []) if str(p).strip()]
        place = places[0] if places else ""
        city = str(entities.get("city") or entities.get("region") or "").strip()
        raw = str(ctx.get("raw_query") or "").strip()
        need = str(ctx.get("primary_information_need") or "unknown")
        tried = set(ctx.get("tried_search_queries") or [])
        hint = _NEED_QUERY_HINTS.get(need, "")

        anchors = ClaimSearchPlanner.dedupe([place, city, hint] + places[:2])
        query_candidates: list[str] = []
        if place and hint:
            query_candidates.append(f"{place} {city} {hint}".strip())
            query_candidates.append(f"{place}{hint}")
        if place and city:
            query_candidates.append(f"{city} {place}")
        if raw and len(raw) <= 48:
            query_candidates.append(raw)
        elif place:
            query_candidates.append(place)
        if refine and place:
            query_candidates.append(f"{place} 攻略")
            query_candidates.append(f"{place} 官方")

        out: list[SearchTask] = []
        for query in ClaimSearchPlanner.dedupe(query_candidates):
            if not query or query in tried:
                continue
            task_anchors = [a for a in anchors if a and (a in query or len(a) >= 2)]
            if place and place not in task_anchors:
                task_anchors.insert(0, place)
            if not task_anchors:
                task_anchors = [query[:12]]
            task = SearchTask(
                task_id=f"{'fallback-refine' if refine else 'fallback'}-{uuid.uuid4().hex[:8]}",
                anchor_keywords=ClaimSearchPlanner.dedupe(task_anchors)[:4],
                search_query=query,
                information_need=need,
                preferred_tool="search_mcp",
                rationale="Rule-based fallback (LLM JSON invalid or empty)",
            )
            from app.agents.keyword_search_agent import KeywordSearchAgent

            try:
                KeywordSearchAgent.validate_task(task)
            except ValueError:
                continue
            out.append(task)
            if len(out) >= max_tasks:
                break

        if not out:
            raise ValueError("Search planner could not produce valid tasks (LLM + fallback)")
        return out

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


def _extract_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _parse_llm_tasks_payload(raw: str) -> dict | None:
    if not raw or not str(raw).strip():
        return None
    blob = _extract_json(str(raw))
    for candidate in (blob, _repair_truncated_json(blob)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _repair_truncated_json(blob: str) -> str | None:
    """Best-effort repair when the model truncates mid-string (common with max_tokens)."""
    text = blob.strip()
    if not text.startswith("{"):
        return None
    if text.endswith("}"):
        return None
    # Close an open string, then close array/object shells.
    repaired = text.rstrip(", \n\r\t")
    if repaired.count('"') % 2 == 1:
        repaired += '"'
    open_brackets = repaired.count("[") - repaired.count("]")
    open_braces = repaired.count("{") - repaired.count("}")
    repaired += "]" * max(0, open_brackets)
    repaired += "}" * max(0, open_braces)
    if repaired == text:
        return None
    return repaired

