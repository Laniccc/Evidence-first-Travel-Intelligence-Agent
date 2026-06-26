"""Phase-2 nearby enrichment: Baidu POI detail ratings + optional review crawlers."""

from __future__ import annotations

import logging

from app.agents.delegated_mcp_runner import run_delegated_mcp
from app.config import get_settings
from app.orchestrator.nearby_category_registry import (
    enrichment_enabled_for_category,
    enrichment_tools_for_category,
    enrichment_top_n_for_category,
    review_enrichment_top_n_for_category,
)
from app.orchestrator.nearby_enrichment_policy import (
    enrichment_candidates_from_evidence,
    requires_nearby_reputation_signal,
    tag_enrichment_claims,
)
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)


def _dianping_review_enabled() -> bool:
    s = get_settings()
    return bool(
        s.enable_nearby_platform_crawlers
        and s.enable_review_crawler_providers
        and s.dianping_crawler_enabled
    )


async def run_nearby_enrichment_after_retrieval(
    *,
    tools_registry,
    state: TravelAgentState,
    base_task: SearchTask,
    nearby_claim: str,
    working_evidence: list,
    prompt_context: dict | None,
    parent_subagent: str = "entity_resolution_agent",
) -> tuple[list, list, int]:
    """Enrich top nearby POIs with ratings (Baidu detail) and optional review crawlers."""
    if not enrichment_enabled_for_category(nearby_claim):
        return [], [], 0

    whitelist = (prompt_context or {}).get("tool_whitelist")
    tools = enrichment_tools_for_category(nearby_claim)
    top_n = enrichment_top_n_for_category(nearby_claim)
    review_n = review_enrichment_top_n_for_category(nearby_claim)
    want_reviews = requires_nearby_reputation_signal(state)

    candidates = enrichment_candidates_from_evidence(working_evidence, nearby_claim, limit=top_n)
    if not candidates:
        return [], [], 0

    all_evidence: list = []
    all_traces: list = []
    tool_call_count = 0

    detail_tool = "baidu_place_detail_mcp"
    if detail_tool in tools and (whitelist is None or whitelist.is_allowed(detail_tool)):
        for idx, row in enumerate(candidates):
            uid = row.get("uid")
            name = str(row.get("name") or "")
            if not uid:
                continue
            detail_task = base_task.model_copy(
                update={
                    "task_id": f"{base_task.task_id}-detail-{idx}",
                    "claim_target": nearby_claim,
                    "information_need": nearby_claim,
                    "lookup_intent": f"补全口碑字段：{name}",
                    "preferred_tool": detail_tool,
                    "tool_parameters": {
                        **(base_task.tool_parameters or {}),
                        "uid": uid,
                        "place_name": name,
                        "city": row.get("city") or (base_task.tool_parameters or {}).get("city"),
                        "information_need": nearby_claim,
                    },
                }
            )
            try:
                ev, tr = await run_delegated_mcp(
                    tools_registry,
                    detail_tool,
                    detail_task,
                    state,
                    prompt_context,
                    subagent=parent_subagent,
                    phase="gap_fill",
                )
                tag_enrichment_claims(
                    ev,
                    poi_uid=str(uid),
                    poi_name=name,
                    information_need=nearby_claim,
                    enrichment_source="baidu_detail",
                )
                all_evidence.extend(ev)
                all_traces.extend(tr)
                tool_call_count += 1
            except Exception as exc:
                logger.warning("nearby detail %s (%s) failed: %s", name, uid, exc)

    review_tool = "dianping_review_crawler_mcp"
    if (
        want_reviews
        and review_n > 0
        and review_tool in tools
        and _dianping_review_enabled()
        and (whitelist is None or whitelist.is_allowed(review_tool))
    ):
        for idx, row in enumerate(candidates[:review_n]):
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            city = row.get("city") or (base_task.tool_parameters or {}).get("city") or state.semantic_frame.entities.city if state.semantic_frame and state.semantic_frame.entities else None
            review_task = base_task.model_copy(
                update={
                    "task_id": f"{base_task.task_id}-review-{idx}",
                    "claim_target": "review_summary",
                    "information_need": "review_summary",
                    "search_query": f"{name} 美食",
                    "lookup_intent": f"用餐评价：{name}",
                    "preferred_tool": review_tool,
                    "tool_parameters": {
                        **(base_task.tool_parameters or {}),
                        "place_name": name,
                        "city": city,
                        "query": name,
                    },
                }
            )
            try:
                ev, tr = await run_delegated_mcp(
                    tools_registry,
                    review_tool,
                    review_task,
                    state,
                    prompt_context,
                    subagent=parent_subagent,
                    phase="gap_fill",
                )
                tag_enrichment_claims(
                    ev,
                    poi_uid=row.get("uid"),
                    poi_name=name,
                    information_need=nearby_claim,
                    enrichment_source="dianping_review",
                )
                all_evidence.extend(ev)
                all_traces.extend(tr)
                tool_call_count += 1
            except Exception as exc:
                logger.warning("nearby review %s failed: %s", name, exc)

    if all_evidence:
        structured = dict(state.structured_result or {})
        runs = list(structured.get("nearby_enrichment_runs") or [])
        runs.append(
            {
                "nearby_claim": nearby_claim,
                "candidate_count": len(candidates),
                "evidence_count": len(all_evidence),
                "want_reviews": want_reviews,
            }
        )
        structured["nearby_enrichment_runs"] = runs[-12:]
        state.structured_result = structured

    return all_evidence, all_traces, tool_call_count
