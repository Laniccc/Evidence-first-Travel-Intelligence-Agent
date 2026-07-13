"""Agent run metrics and tool trace rollups."""

from pydantic import BaseModel, Field

from app.observability.tool_trace import ToolTrace


class AgentRunMetrics(BaseModel):
    tool_calls: int = Field(default=0, ge=0)
    failed_tool_calls: int = Field(default=0, ge=0)
    total_latency_ms: float = Field(default=0.0, ge=0.0)
    fallback_count: int = Field(default=0, ge=0)
    cache_hit_count: int = Field(default=0, ge=0)


def tool_trace_metrics(tool_traces: list[ToolTrace | dict]) -> AgentRunMetrics:
    normalized = [
        trace if isinstance(trace, ToolTrace) else ToolTrace.model_validate(trace)
        for trace in tool_traces
    ]
    return AgentRunMetrics(
        tool_calls=len(normalized),
        failed_tool_calls=sum(1 for trace in normalized if trace.status != "ok"),
        total_latency_ms=sum(float(trace.latency_ms or 0.0) for trace in normalized),
        fallback_count=sum(1 for trace in normalized if trace.fallback_used),
        cache_hit_count=sum(1 for trace in normalized if trace.cache_hit),
    )
