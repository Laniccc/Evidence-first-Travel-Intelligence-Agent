from __future__ import annotations

from typing import Any


def evidence_list_from_gateway(items: list[dict[str, Any]]) -> list[Any]:
    from app.schemas.evidence import Evidence

    result: list[Any] = []
    for item in items or []:
        try:
            result.append(Evidence.model_validate(item))
        except Exception:
            continue
    return result


def tool_trace_from_gateway(trace: dict[str, Any] | None, tool_name: str, payload: dict[str, Any]):
    from app.schemas.tool_trace import ToolTrace

    if not trace:
        return ToolTrace(
            tool_name=tool_name,
            input=payload,
            status="error",
            error="missing tool_trace from Java gateway",
        )
    return ToolTrace(
        tool_name=trace.get("tool_name") or tool_name,
        input=trace.get("input") or payload,
        evidence_ids=list(trace.get("evidence_ids") or []),
        latency_ms=float(trace.get("latency_ms") or 0.0),
        status=trace.get("status") or "ok",
        error=trace.get("error"),
        fallback_used=bool(trace.get("fallback_used", False)),
        cache_hit=bool(trace.get("cache_hit", False)),
    )
