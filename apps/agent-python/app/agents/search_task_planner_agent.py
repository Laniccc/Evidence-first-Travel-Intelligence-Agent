"""S5 sub-agent: LLM plans keyword-anchored search tasks for A2A dispatch."""

from __future__ import annotations

import json
import logging
import uuid

from app.config import get_settings
from app.llm_client import LLMClient
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)

_SYSTEM_INITIAL = """You plan keyword search tasks for a travel evidence agent (China).
Return ONLY JSON:
{"tasks":[{"anchor_keywords":["..."],"search_query":"...","information_need":"ticket_price","rationale":"...","preferred_tool":"search_mcp"}]}

Rules:
- Propose 2-3 search tasks tailored to the user's question, anchor_keywords, and claim_types.
- information_need = search purpose passed to keyword_search_agent (e.g. ticket_price, opening_hours).
- anchor_keywords: strict tokens from user place/need; search_query MUST contain at least one anchor.
- If place_candidates shows multiple regions for the same name, create separate tasks per likely region
  (e.g. 五彩滩 阿勒泰 门票 vs 五彩滩 北海 门票) — do NOT ask the user here.
- preferred_tool is optional hint only; keyword_search_agent will pick MCP from whitelist.
- Do NOT answer the user; only plan searches."""

_SYSTEM_REFINE = """You refine keyword search tasks after prior keyword_search_agent runs.
Return ONLY JSON:
{"tasks":[{"anchor_keywords":["..."],"search_query":"...","information_need":"ticket_price","rationale":"...","preferred_tool":"search_mcp"}]}
Rules:
- Use the top-level key "tasks" (NOT new_tasks).
- Return 1-2 NEW tasks only.
- Read anchor_keywords, place_candidates, evidence_highlights, recent_keyword_search_results.
- Combine S4 user keywords with subagent results; adjust search_query and information_need for next lookups.
- Do NOT repeat tried_search_queries.
- If place ambiguity remains, narrow queries by region/city from place_candidates or evidence.
- preferred_tool is optional; subagent selects MCP."""

_REPAIR_SUFFIX = (
    "\n\nYour previous reply was invalid or empty. "
    "Return ONLY a single JSON object matching the schema above."
)


class SearchTaskPlannerAgent:
    """LLM decomposition into keyword_search_agent tasks."""

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
        cap = int(ctx.get("max_keyword_searches") or 10)
        max_tasks = 2 if refine else min(3, cap)
        user = json.dumps(_planner_user_payload(ctx, refine), ensure_ascii=False)
        settings = get_settings()
        max_tokens = settings.llm_planner_max_tokens

        raw = await self.llm.complete(
            system=system,
            user=user,
            max_tokens=max_tokens,
            json_only=True,
        )
        tasks = self._tasks_from_payload(raw, ctx, refine=refine, max_tasks=max_tasks)
        if tasks:
            return tasks

        logger.warning("SearchTaskPlannerAgent: first LLM reply had no valid tasks; repairing")
        repair_user = json.dumps(
            {
                "previous_error": "no_valid_tasks",
                "planner_input": _planner_user_payload(ctx, refine),
            },
            ensure_ascii=False,
        )
        raw = await self.llm.complete(
            system=system + _REPAIR_SUFFIX,
            user=repair_user,
            max_tokens=max_tokens,
            json_only=True,
        )
        tasks = self._tasks_from_payload(raw, ctx, refine=refine, max_tasks=max_tasks)
        if not tasks:
            logger.error(
                "SearchTaskPlannerAgent repair failed; raw preview=%r",
                (raw or "")[:800],
            )
            raise ValueError(
                "SearchTaskPlannerAgent could not produce valid tasks after LLM repair "
                f"(raw_len={len(raw or '')})"
            )
        return tasks

    def _tasks_from_payload(
        self,
        raw: str,
        ctx: dict,
        *,
        refine: bool,
        max_tasks: int,
    ) -> list[SearchTask]:
        data = _parse_llm_tasks_payload(raw)
        if data is None:
            return []

        bucket = _normalize_tasks_bucket(data)
        if not bucket:
            return []

        need = ctx.get("primary_information_need") or "unknown"
        tried = set(ctx.get("tried_search_queries") or [])
        out: list[SearchTask] = []
        for item in bucket:
            if not isinstance(item, dict):
                continue
            coerced = _coerce_planner_task(item, ctx, need)
            if coerced is None:
                continue
            anchor_tokens, query, information_need = coerced
            if not query or query in tried:
                continue
            task = SearchTask(
                task_id=f"{'refine' if refine else 'search'}-{uuid.uuid4().hex[:8]}",
                anchor_keywords=anchor_tokens,
                search_query=query,
                information_need=information_need,
                preferred_tool=str(item.get("preferred_tool") or "search_mcp"),
                rationale=str(item.get("rationale") or ("LLM refine" if refine else "LLM planned")),
            )
            from app.agents.keyword_search_agent import KeywordSearchAgent

            try:
                KeywordSearchAgent.validate_task(task)
            except ValueError as exc:
                logger.warning(
                    "SearchTaskPlannerAgent: dropped task after validation: %s query=%r anchors=%r",
                    exc,
                    query,
                    anchor_tokens,
                )
                continue
            out.append(task)
            if len(out) >= max_tasks:
                break
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


def _planner_user_payload(ctx: dict, refine: bool) -> dict:
    """Minimal fields the planner needs — avoid dumping full S5 state into the prompt."""
    payload: dict = {
        "raw_query": ctx.get("raw_query"),
        "normalized_request": ctx.get("normalized_request"),
        "anchor_keywords": ctx.get("anchor_keywords") or [],
        "gated_search_keywords": ctx.get("gated_search_keywords") or [],
        "place_ambiguity": ctx.get("place_ambiguity"),
        "labeled_entities": (ctx.get("labeled_entities") or [])[:8],
        "primary_information_need": ctx.get("primary_information_need"),
        "claim_types": ctx.get("claim_types") or [],
        "entities": ctx.get("entities") or {},
        "tried_search_queries": ctx.get("tried_search_queries") or [],
        "keyword_search_count": ctx.get("keyword_search_count"),
        "max_keyword_searches": ctx.get("max_keyword_searches"),
    }
    if refine:
        payload["place_candidates"] = (ctx.get("place_candidates") or [])[:4]
        payload["recent_keyword_search_results"] = (ctx.get("recent_keyword_search_results") or [])[:3]
        payload["evidence_highlights"] = (ctx.get("evidence_highlights") or [])[:3]
        payload["existing_tasks"] = (ctx.get("existing_tasks") or [])[-3:]
    return payload


def _coerce_planner_task(
    item: dict,
    ctx: dict,
    default_need: str,
) -> tuple[list[str], str, str] | None:
    """Normalize LLM task fields and align search_query with S3 anchor keywords."""
    query = str(
        item.get("search_query")
        or item.get("query")
        or item.get("searchQuery")
        or ""
    ).strip()

    raw_anchors = (
        item.get("anchor_keywords")
        or item.get("anchors")
        or item.get("keywords")
        or []
    )
    if isinstance(raw_anchors, str):
        raw_anchors = [raw_anchors]

    anchor_tokens = ClaimSearchPlanner.dedupe(
        [str(a).strip() for a in raw_anchors if str(a).strip()]
        + [str(a).strip() for a in (ctx.get("anchor_keywords") or []) if str(a).strip()]
        + [str(a).strip() for a in (ctx.get("gated_search_keywords") or []) if str(a).strip()]
    )
    entities = ctx.get("entities") or {}
    for place in entities.get("places") or []:
        token = str(place).strip()
        if token and token not in anchor_tokens:
            anchor_tokens.append(token)
    for region in (entities.get("city"), entities.get("region")):
        token = str(region or "").strip()
        if token and token not in anchor_tokens:
            anchor_tokens.append(token)

    anchor_tokens = [a for a in anchor_tokens if len(a) >= 2]
    if not anchor_tokens:
        return None

    if not query:
        query = str(ctx.get("raw_query") or "").strip()
    if not query:
        query = " ".join(anchor_tokens[:3])

    information_need = str(
        item.get("information_need") or item.get("need") or default_need
    ).strip() or default_need

    if not _query_contains_anchor(query, anchor_tokens):
        query = f"{anchor_tokens[0]} {query}".strip()

    return anchor_tokens[:6], query[:96], information_need


def _query_contains_anchor(query: str, anchors: list[str]) -> bool:
    for anchor in anchors:
        if len(anchor) < 2:
            continue
        if anchor in query:
            return True
    return False


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


def _normalize_tasks_bucket(data: dict | list) -> list:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    bucket = None
    for key in ("tasks", "new_tasks", "search_tasks", "refined_tasks"):
        candidate = data.get(key)
        if candidate is not None:
            bucket = candidate
            break
    if isinstance(bucket, dict):
        return [bucket]
    if isinstance(bucket, list):
        return [item for item in bucket if isinstance(item, dict)]
    return []


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
        if isinstance(data, list):
            return {"tasks": data}
    return None


def _repair_truncated_json(blob: str) -> str | None:
    """Best-effort repair when the model truncates mid-string (common with max_tokens)."""
    text = blob.strip()
    if not text.startswith("{"):
        return None
    if text.endswith("}"):
        return None
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
