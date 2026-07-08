"""Shared MCP invocation helpers for S5 functional sub-agents."""

from __future__ import annotations

from app.orchestrator.mcp_tool_arguments import enrich_mcp_tool_arguments
from app.orchestrator.s5_diversified_tool_selector import select_tool_for_subagent
from app.orchestrator.s5_tool_attempt_ledger import Phase, record_tool_attempt
from app.schemas.search_task import SearchTask
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name


def pick_tool_from_priority(
    priority: list[str],
    whitelist: ToolWhitelist | None,
    *,
    preferred: str | None = None,
    state: TravelAgentState | None = None,
    claim_type: str | None = None,
    subagent: str | None = None,
    phase: Phase = "main",
) -> str | None:
    if state is not None and claim_type:
        from app.orchestrator.s5_diversified_tool_selector import S5DiversifiedToolSelector

        selector = S5DiversifiedToolSelector(state)
        sel = selector.select_next(claim_type, whitelist, subagent=subagent, phase=phase)
        if sel:
            return sel.tool_name

    if preferred:
        resolved = resolve_tool_name(preferred)
        if whitelist is None or whitelist.is_allowed(resolved):
            return resolved
    for tool in priority:
        resolved = resolve_tool_name(tool)
        if whitelist is None or whitelist.is_allowed(resolved):
            return resolved
    if whitelist is not None:
        allowed = whitelist.allowed_tool_names()
        if allowed:
            return allowed[0]
    return None


async def run_delegated_mcp(
    tools_registry,
    tool_name: str,
    task: SearchTask,
    state: TravelAgentState,
    prompt_context: dict | None,
    *,
    subagent: str | None = None,
    phase: Phase = "main",
) -> tuple[list, list]:
    payload = dict(task.tool_parameters or {})
    if task.search_query.strip():
        payload["query"] = task.search_query.strip()
    elif task.lookup_intent.strip():
        payload.setdefault("query", task.lookup_intent.strip()[:200])
    if task.information_need:
        payload.setdefault("information_need", task.information_need)
    if task.claim_target:
        payload.setdefault("claim_target", task.claim_target)

    selection = select_tool_for_subagent(
        state,
        task,
        (prompt_context or {}).get("tool_whitelist"),
        subagent=subagent or "delegated_mcp",
        phase="gap_fill" if (prompt_context or {}).get("gap_filling") else phase,
    )
    if selection:
        payload.update(selection.tool_parameters_patch)
        tool_name = selection.tool_name

    phase_eff: Phase = "gap_fill" if (prompt_context or {}).get("gap_filling") else phase
    claim = task.claim_target or task.information_need
    try:
        payload = enrich_mcp_tool_arguments(
            tool_name,
            payload,
            state=state,
            prompt_context=prompt_context or {},
        )
    except ValueError as exc:
        record_tool_attempt(
            state,
            tool_name=tool_name,
            claim_type=str(claim) if claim else None,
            subagent=subagent,
            phase=phase_eff,
            status="skipped_invalid_args",
            evidence_count=0,
            error=str(exc),
        )
        return [], []
    trace_before = len(tools_registry.traces)

    evidence = await tools_registry.run_tool(tool_name, **payload)
    new_traces = tools_registry.traces[trace_before:]
    status = "ok" if evidence else "zero_evidence"
    for tr in new_traces:
        if isinstance(tr, dict):
            if tr.get("output_parse_status") == "parse_error" or (
                tr.get("status") == "error" and not evidence
            ):
                status = "error"
                break
        else:
            if tr.output_parse_status == "parse_error" or (tr.status == "error" and not evidence):
                status = "error"
                break
    record_tool_attempt(
        state,
        tool_name=tool_name,
        claim_type=str(claim) if claim else None,
        subagent=subagent,
        phase=phase_eff,
        status=status,
        evidence_count=len(evidence),
    )
    return list(evidence), [t.model_dump() for t in new_traces]
