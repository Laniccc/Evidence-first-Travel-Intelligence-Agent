import asyncio

import pytest

from app.orchestration.state_audit import InMemoryStateAuditStore
from app.orchestration.state_contracts import (
    AgentState,
    FailureClass,
    StateContext,
    StateFailure,
    StatePolicy,
    StateResult,
)
from app.orchestration.state_runtime import StateRuntime


def context_for(query: str = "故宫开放时间") -> StateContext:
    return StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query=query,
    )


class HandlerReturning:
    def __init__(self, result: StateResult):
        self.result = result
        self.calls = 0

    async def run(self, context: StateContext) -> StateResult:
        self.calls += 1
        return self.result


class TimeoutOnceHandler:
    def __init__(self):
        self.calls = 0

    async def run(self, context: StateContext) -> StateResult:
        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(0.05)
        return StateResult.succeeded(next_state=AgentState.CONTEXT)


@pytest.mark.asyncio
async def test_runtime_rejects_illegal_transition_and_audits_failure():
    audit = InMemoryStateAuditStore()
    runtime = StateRuntime(
        handlers={
            AgentState.INGRESS: HandlerReturning(
                StateResult.succeeded(next_state=AgentState.COMPOSE)
            )
        },
        audit=audit,
    )

    result = await runtime.run(context_for())

    assert result.terminal_state is AgentState.FAILED
    assert result.failure is not None
    assert result.failure.code == "illegal_transition"
    assert [event.event_type for event in audit.events] == [
        "phase_started",
        "phase_succeeded",
        "phase_failed",
    ]


@pytest.mark.asyncio
async def test_timeout_is_retried_once_and_recovery_is_audited():
    audit = InMemoryStateAuditStore()
    handler = TimeoutOnceHandler()
    runtime = StateRuntime(
        handlers={
            AgentState.INGRESS: handler,
            AgentState.CONTEXT: HandlerReturning(
                StateResult.succeeded(next_state=AgentState.SAFE_FAILURE)
            ),
        },
        audit=audit,
        policies={
            AgentState.INGRESS: StatePolicy(timeout_seconds=0.01, max_attempts=2),
        },
    )

    result = await runtime.run(context_for())

    assert result.terminal_state is AgentState.SAFE_FAILURE
    assert handler.calls == 2
    assert any(event.event_type == "phase_recovered" for event in audit.events)
    assert [event.attempt for event in audit.events if event.state is AgentState.INGRESS and event.event_type == "phase_started"] == [1, 2]


@pytest.mark.asyncio
async def test_non_retryable_failure_stops_without_second_attempt():
    handler = HandlerReturning(
        StateResult.failed(
            failure=StateFailure(
                category=FailureClass.VALIDATION,
                code="invalid_query",
                message="query is invalid",
                recoverable=False,
            )
        )
    )
    runtime = StateRuntime(
        handlers={AgentState.INGRESS: handler},
        audit=InMemoryStateAuditStore(),
        policies={AgentState.INGRESS: StatePolicy(max_attempts=2)},
    )

    result = await runtime.run(context_for(""))

    assert result.terminal_state is AgentState.FAILED
    assert result.failure.code == "invalid_query"
    assert handler.calls == 1


@pytest.mark.asyncio
async def test_max_steps_prevents_unbounded_state_loop():
    runtime = StateRuntime(
        handlers={
            AgentState.INGRESS: HandlerReturning(
                StateResult.succeeded(next_state=AgentState.CONTEXT)
            ),
            AgentState.CONTEXT: HandlerReturning(
                StateResult.succeeded(next_state=AgentState.UNDERSTAND)
            ),
            AgentState.UNDERSTAND: HandlerReturning(
                StateResult.succeeded(next_state=AgentState.ROUTE)
            ),
        },
        audit=InMemoryStateAuditStore(),
        max_steps=2,
    )

    result = await runtime.run(context_for())

    assert result.terminal_state is AgentState.FAILED
    assert result.failure.code == "max_steps_exceeded"


@pytest.mark.asyncio
async def test_terminal_state_is_not_dispatched_to_a_handler():
    terminal_handler = HandlerReturning(
        StateResult.succeeded(next_state=AgentState.DELIVER)
    )
    runtime = StateRuntime(
        handlers={
            AgentState.INGRESS: HandlerReturning(
                StateResult.succeeded(next_state=AgentState.SAFE_FAILURE)
            ),
            AgentState.SAFE_FAILURE: terminal_handler,
        },
        audit=InMemoryStateAuditStore(),
    )

    result = await runtime.run(context_for())

    assert result.terminal_state is AgentState.SAFE_FAILURE
    assert terminal_handler.calls == 0
