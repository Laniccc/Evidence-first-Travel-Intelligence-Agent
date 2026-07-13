from app.governance import (
    ConfidenceCalculator,
    CostMetric,
    CostPolicy,
    FailureCategory,
    FailureReason,
    QualityGateResult,
    SafetyPolicy,
    ToolBudget,
)
from app.observability import ToolTrace, TraceRecorder, debug_session_path, tool_trace_metrics
from app.orchestration.travel_agent_state import TravelAgentState


def test_governance_models_enforce_cost_and_tool_budgets():
    policy = CostPolicy(max_llm_calls=2, max_tool_calls=3, max_estimated_cost_usd=0.25)
    allowed_metric = CostMetric(llm_calls=1, tool_calls=2, estimated_cost_usd=0.1)
    blocked_metric = CostMetric(llm_calls=3, tool_calls=2, estimated_cost_usd=0.1)
    budget = ToolBudget(max_calls=2)

    assert policy.allows(allowed_metric)
    assert not policy.allows(blocked_metric)
    assert budget.remaining_calls == 2
    assert budget.consume().remaining_calls == 1


def test_quality_safety_and_failure_reason_models_are_available():
    gate = QualityGateResult.from_threshold(0.8, threshold=0.7, reasons=["enough evidence"])
    safety = SafetyPolicy(blocked_tool_names={"unsafe_tool"})
    failure = FailureReason(
        category=FailureCategory.TOOL,
        code="tool_timeout",
        message="Tool timed out",
    )

    assert gate.passed
    assert safety.allows_tool("search_mcp")
    assert not safety.allows_tool("unsafe_tool")
    assert failure.recoverable


def test_observability_trace_and_metrics_surfaces_are_available():
    state = TravelAgentState(
        session_id="session-1",
        query_id="query-1",
        raw_user_query="What evidence is available?",
    )
    TraceRecorder.add(state, "started")
    metrics = tool_trace_metrics(
        [
            ToolTrace(tool_name="search_mcp", latency_ms=120.0, status="ok", cache_hit=True),
            ToolTrace(tool_name="weather_mcp", latency_ms=80.0, status="error", fallback_used=True),
        ]
    )

    assert state.visible_trace == ["started"]
    assert metrics.tool_calls == 2
    assert metrics.failed_tool_calls == 1
    assert metrics.total_latency_ms == 200.0
    assert metrics.fallback_count == 1
    assert metrics.cache_hit_count == 1
    assert debug_session_path().name == "debug_last_session.md"


def test_governance_exposes_confidence_policy():
    evidence = type(
        "Evidence",
        (),
        {"confidence": 0.8, "claims": [type("Claim", (), {"confidence": 0.6})()]},
    )()

    assert ConfidenceCalculator.from_evidence([evidence]) == 0.7
    assert ConfidenceCalculator.combine(0.6, 0.8) == 0.7
