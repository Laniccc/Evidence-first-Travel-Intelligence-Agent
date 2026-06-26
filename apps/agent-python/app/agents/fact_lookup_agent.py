"""fact_lookup_agent — phase/source_family runner for LookupResearchChain."""

from __future__ import annotations

from typing import Any

from app.agents.fact_lookup_phase_runner import run_lookup_phase
from app.orchestrator.fact_lookup_policy import is_fact_lookup_task, primary_fact_need_from_state
from app.orchestrator.lookup_research_chain import (
    ensure_lookup_chain_initialized,
    is_duplicate_lookup_attempt,
    lookup_attempt_signature,
    record_lookup_attempt,
)
from app.schemas.lookup_research_chain import LookupPhase, LookupQueryObjective, SourceFamily
from app.schemas.user_query import TravelAgentState


def _normalize_query_objectives(raw: Any) -> list[dict] | None:
    if raw is None:
        return None
    if isinstance(raw, LookupQueryObjective):
        return [raw.model_dump()]
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, str):
        return [{"objective": raw, "source_family": "web_reference"}]
    if not isinstance(raw, list):
        return None
    out: list[dict] = []
    for item in raw:
        if isinstance(item, LookupQueryObjective):
            out.append(item.model_dump())
        elif isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({"objective": item})
    return out or None


def _objective_key(query_objectives: list[dict] | None, source_family: str) -> str:
    if not query_objectives:
        return source_family
    first = query_objectives[0]
    if isinstance(first, dict):
        return str(first.get("objective") or first.get("query_intent") or source_family)
    return str(first or source_family)


class FactLookupAgent:
    def __init__(self, tools_registry=None) -> None:
        self.tools = tools_registry

    async def run(
        self,
        state: TravelAgentState,
        arguments: dict | None = None,
        prompt_context: dict | None = None,
    ) -> dict[str, Any]:
        args = arguments or {}
        if not is_fact_lookup_task(state):
            return {"subagent": "fact_lookup_agent", "evidence": [], "tool_traces": []}
        if not self.tools:
            return {
                "subagent": "fact_lookup_agent",
                "evidence": [],
                "tool_traces": [],
                "error": "tools_registry required",
            }

        ensure_lookup_chain_initialized(state)
        lookup_phase: LookupPhase = args.get("lookup_phase") or "fact_acquisition"
        source_family: SourceFamily = args.get("source_family") or "web_reference"
        claim_target = args.get("claim_target") or primary_fact_need_from_state(state)
        query_objectives = _normalize_query_objectives(args.get("query_objectives"))

        sig = lookup_attempt_signature(
            subagent="fact_lookup_agent",
            claim_type=claim_target,
            phase=lookup_phase,
            source_family=source_family,
            objective=_objective_key(query_objectives, source_family),
        )
        if is_duplicate_lookup_attempt(state, sig):
            return {
                "subagent": "fact_lookup_agent",
                "skipped": True,
                "reason": "duplicate_lookup_attempt",
                "evidence": [],
                "tool_traces": [],
            }
        record_lookup_attempt(state, sig)

        return await run_lookup_phase(
            tools_registry=self.tools,
            state=state,
            lookup_phase=lookup_phase,
            source_family=source_family,
            claim_target=claim_target,
            query_objectives=query_objectives,
            chain_updates=args.get("lookup_research_chain_update"),
            prompt_context=prompt_context,
            task_id=str(args.get("task_id") or "fact-lookup"),
        )
