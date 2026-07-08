"""S5 sub-agent: LLM plans keyword-anchored search tasks for A2A dispatch."""

from __future__ import annotations

import json
import logging
import uuid

from app.config import get_settings
from app.llm_client import LLMClient
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.search_query_rewriter import SearchQueryRewriter
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)

_SYSTEM_INITIAL = """You plan evidence lookup tasks for a travel evidence agent (China).
Return ONLY JSON:
{"tasks":[{"lookup_intent":"...","claim_target":"opening_hours","search_query":"...","anchor_keywords":["..."],"information_need":"opening_hours","preferred_tool":"search_mcp","tool_parameters":{},"rationale":"..."}]}

Query rewrite rules (do NOT paste user raw query verbatim):
1. Read query_rewrite_slots: anchor_entity, primary_intent, claim_types, time_hint, user_need_phrase.
2. Read query_rewrite_plan: rule-based multi-query angles per claim — each task targets ONE evidence angle.
3. search_query = place_entity + intent_words + source_hint + time_hint (when needed).
   Formula: {place} + {claim_keyword} + {official|游客评价|怎么去|...} + {今年|今天|...}
4. Different tasks = different evidence goals (not synonym repeats).
5. lookup_intent: what evidence this query should retrieve (one sentence).
6. LOOKUP/hard-fact: prefer 官方/官网/游客服务; REVIEW_CHECK: 游客评价/避坑/大众点评; REALTIME: 最新/今天/通知.
7. Route/day-trip: preferred_tool=baidu_route_mcp + tool_parameters.origin+destination.
8. Supplement query_rewrite_plan only if a critical angle is missing; do NOT duplicate rule queries.
9. Do NOT answer the user; only plan delegated lookups."""

_SYSTEM_REFINE = """You refine evidence lookup tasks after prior keyword_search_agent runs.
Return ONLY JSON:
{"tasks":[{"lookup_intent":"...","claim_target":"ticket_price","search_query":"...","anchor_keywords":["..."],"information_need":"ticket_price","preferred_tool":"search_mcp","tool_parameters":{},"rationale":"..."}]}
Rules:
- Use "tasks" (NOT new_tasks). Return 1-2 NEW tasks only.
- Read query_rewrite_plan and tried_search_queries — pick untried claim angles.
- Each search_query must target a different evidence goal (official vs review vs route).
- Do NOT repeat queries from query_rewrite_plan or tried_search_queries.
- If distance/duration missing: baidu_route_mcp with tool_parameters.origin+destination."""

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

        cap = int(ctx.get("max_keyword_searches") or 10)
        max_tasks = min(3, cap)
        rewriter = SearchQueryRewriter.from_planning_context(ctx, state)
        rule_tasks = rewriter.to_search_tasks(max_tasks=max_tasks)
        if len(rule_tasks) >= max_tasks:
            return self._dedupe_tasks(rule_tasks)

        llm_tasks = await self._llm_plan_tasks(
            ctx, refine=False, max_tasks=max(0, max_tasks - len(rule_tasks))
        )
        return self._dedupe_tasks(rule_tasks + llm_tasks)[:max_tasks]

    async def _llm_plan_tasks(
        self,
        ctx: dict,
        *,
        refine: bool,
        max_tasks: int | None = None,
    ) -> list[SearchTask]:
        system = _SYSTEM_REFINE if refine else _SYSTEM_INITIAL
        cap = int(ctx.get("max_keyword_searches") or 10)
        if max_tasks is None:
            max_tasks = 2 if refine else min(3, cap)
        if max_tasks <= 0:
            return []
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
            anchor_tokens, query, information_need, lookup_intent, claim_target, tool_params = coerced
            if not query or query in tried:
                continue
            task = SearchTask(
                task_id=f"{'refine' if refine else 'search'}-{uuid.uuid4().hex[:8]}",
                lookup_intent=lookup_intent,
                claim_target=claim_target or information_need,
                anchor_keywords=anchor_tokens,
                search_query=query,
                information_need=information_need,
                preferred_tool=str(item.get("preferred_tool") or "search_mcp"),
                tool_parameters=tool_params,
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
        "user_need_residual": ctx.get("user_need_residual"),
        "query_rewrite_slots": ctx.get("query_rewrite_slots") or {},
        "query_rewrite_plan": (ctx.get("query_rewrite_plan") or [])[:8],
        "agent_tool_definitions": (ctx.get("agent_tool_definitions") or [])[:12],
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
) -> tuple[list[str], str, str, str, str, dict[str, str]] | None:
    """Normalize LLM task fields into delegated lookup payload."""
    lookup_intent = str(
        item.get("lookup_intent")
        or item.get("evidence_goal")
        or item.get("rationale")
        or ""
    ).strip()
    claim_target = str(item.get("claim_target") or item.get("claim_type") or "").strip()

    raw_params = item.get("tool_parameters") or item.get("tool_args") or {}
    tool_params: dict[str, str] = {}
    if isinstance(raw_params, dict):
        from app.schemas.search_task import normalize_tool_parameters

        tool_params = normalize_tool_parameters(raw_params)

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
    route_ready = bool(tool_params.get("origin") and tool_params.get("destination"))
    if not anchor_tokens and route_ready:
        for token in (tool_params.get("origin"), tool_params.get("destination")):
            t = str(token or "").strip()
            if len(t) >= 2 and t not in anchor_tokens:
                anchor_tokens.append(t)
    if not anchor_tokens and not route_ready:
        return None

    if not query:
        query = str(ctx.get("raw_query") or "").strip()
    if not query:
        query = " ".join(anchor_tokens[:3])

    information_need = str(
        item.get("information_need") or item.get("need") or claim_target or default_need
    ).strip() or default_need
    if not claim_target:
        claim_target = information_need

    if not lookup_intent:
        lookup_intent = query or " ".join(anchor_tokens[:3])

    if not query:
        query = lookup_intent[:96]
    if not query:
        query = " ".join(anchor_tokens[:3])

    if not _query_contains_anchor(query, anchor_tokens) and not (
        tool_params.get("origin") and tool_params.get("destination")
    ):
        query = f"{anchor_tokens[0]} {query}".strip()

    if ctx.get("comparison_mode") and ctx.get("comparison_active_place"):
        from app.orchestrator.comparison_helpers import build_comparison_search_query
        from app.schemas.semantic_frame import SemanticFrame, SemanticEntities

        place = str(ctx["comparison_active_place"])
        frame_stub = SemanticFrame(
            raw_query=str(ctx.get("raw_query") or ""),
            normalized_request=str(ctx.get("normalized_request") or ""),
            entities=SemanticEntities.model_validate(ctx.get("entities") or {}),
        )
        query = build_comparison_search_query(
            place,
            information_need,
            frame_stub,
            peer_places=list(ctx.get("comparison_peer_places") or []),
            user_query=str(ctx.get("raw_query") or ""),
        )

    return anchor_tokens[:6], query[:96], information_need, lookup_intent[:200], claim_target, tool_params


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
