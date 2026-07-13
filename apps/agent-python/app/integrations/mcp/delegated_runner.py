"""Shared MCP invocation helpers for delegated S5 sub-agents."""

from __future__ import annotations

import importlib
from typing import Any


def _module(name: str):
    return importlib.import_module(name)


def _resolve_tool_name(tool_name: str) -> str:
    return _module("app.tools.tool_name_resolver").resolve_tool_name(tool_name)


def pick_tool_from_priority(
    priority: list[str],
    whitelist: Any | None,
    *,
    preferred: str | None = None,
    state: Any | None = None,
    claim_type: str | None = None,
    subagent: str | None = None,
    phase: str = "main",
) -> str | None:
    if state is not None and claim_type:
        selector_cls = _module(
            "app.execution.s5_diversified_tool_selector"
        ).S5DiversifiedToolSelector
        selector = selector_cls(state)
        selection = selector.select_next(claim_type, whitelist, subagent=subagent, phase=phase)
        if selection:
            return selection.tool_name

    if preferred:
        resolved = _resolve_tool_name(preferred)
        if whitelist is None or whitelist.is_allowed(resolved):
            return resolved
    for tool in priority:
        resolved = _resolve_tool_name(tool)
        if whitelist is None or whitelist.is_allowed(resolved):
            return resolved
    if whitelist is not None:
        allowed = whitelist.allowed_tool_names()
        if allowed:
            return allowed[0]
    return None


async def run_delegated_mcp(
    tools_registry: Any,
    tool_name: str,
    task: Any,
    state: Any,
    prompt_context: dict | None,
    *,
    subagent: str | None = None,
    phase: str = "main",
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

    selector_module = _module("app.execution.s5_diversified_tool_selector")
    selection = selector_module.select_tool_for_subagent(
        state,
        task,
        (prompt_context or {}).get("tool_whitelist"),
        subagent=subagent or "delegated_mcp",
        phase="gap_fill" if (prompt_context or {}).get("gap_filling") else phase,
    )
    if selection:
        payload.update(selection.tool_parameters_patch)
        tool_name = selection.tool_name

    effective_phase = "gap_fill" if (prompt_context or {}).get("gap_filling") else phase
    claim = task.claim_target or task.information_need
    try:
        payload = _module("app.integrations.mcp.tool_arguments").enrich_mcp_tool_arguments(
            tool_name,
            payload,
            state=state,
            prompt_context=prompt_context or {},
        )
    except ValueError as exc:
        _module("app.execution.s5_tool_attempt_ledger").record_tool_attempt(
            state,
            tool_name=tool_name,
            claim_type=str(claim) if claim else None,
            subagent=subagent,
            phase=effective_phase,
            status="skipped_invalid_args",
            evidence_count=0,
            error=str(exc),
        )
        return [], []
    trace_before = len(tools_registry.traces)

    evidence = await tools_registry.run_tool(tool_name, **payload)
    new_traces = tools_registry.traces[trace_before:]
    status = "ok" if evidence else "zero_evidence"
    for trace in new_traces:
        if isinstance(trace, dict):
            if trace.get("output_parse_status") == "parse_error" or (
                trace.get("status") == "error" and not evidence
            ):
                status = "error"
                break
        else:
            if trace.output_parse_status == "parse_error" or (
                trace.status == "error" and not evidence
            ):
                status = "error"
                break
    _module("app.execution.s5_tool_attempt_ledger").record_tool_attempt(
        state,
        tool_name=tool_name,
        claim_type=str(claim) if claim else None,
        subagent=subagent,
        phase=effective_phase,
        status=status,
        evidence_count=len(evidence),
    )
    return list(evidence), [trace.model_dump() for trace in new_traces]


__all__ = ["pick_tool_from_priority", "run_delegated_mcp"]
