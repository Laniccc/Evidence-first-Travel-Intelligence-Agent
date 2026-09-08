"""Shared handler execution policy; scheduling belongs to the selected runtime."""
from __future__ import annotations

import asyncio
import time

from app.orchestration.state_audit import StateAuditEvent, StateAuditStore
from app.orchestration.state_contracts import (
    AgentState, FailureClass, RecoveryRecord, StateContext, StateFailure,
    StateHandler, StatePolicy, StateResult,
)


async def execute_state_handler(
    context: StateContext,
    state: AgentState,
    handler: StateHandler,
    policy: StatePolicy,
    audit: StateAuditStore,
) -> tuple[StateResult, int, FailureClass | None]:
    recovered_from: FailureClass | None = None
    for attempt in range(1, policy.max_attempts + 1):
        audit.append(StateAuditEvent.started(context, state, attempt=attempt))
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                handler.run(context),
                timeout=policy.timeout_seconds,
            )
        except TimeoutError:
            result = StateResult.failed(
                failure=StateFailure(
                    category=FailureClass.TIMEOUT,
                    code="timeout",
                    message=f"State {state.value} exceeded {policy.timeout_seconds}s",
                    recoverable=True,
                )
            )
        except Exception as exc:
            result = StateResult.failed(
                failure=StateFailure(
                    category=FailureClass.INTERNAL,
                    code="unhandled_state_error",
                    message=f"State {state.value} raised {type(exc).__name__}",
                    recoverable=False,
                )
            )

        duration_ms = (time.perf_counter() - started) * 1000
        if result.status != "failed":
            recovery = result.recovery
            if recovered_from is not None and recovery is None:
                recovery = RecoveryRecord(
                    strategy="retry_once",
                    recovered_from=recovered_from,
                    attempt=attempt,
                )
            audit.append(
                StateAuditEvent.completed(
                    context,
                    state,
                    attempt=attempt,
                    output=result.output,
                    duration_ms=duration_ms,
                    recovered=recovery,
                )
            )
            if recovery is not None:
                result = result.model_copy(update={"status": "recovered", "recovery": recovery})
            return result, attempt, recovered_from

        failure = result.failure or StateFailure(
            category=FailureClass.INTERNAL,
            code="missing_failure",
            message="Failed state returned no failure detail",
            recoverable=False,
        )
        audit.append(
            StateAuditEvent.failed(
                context,
                state,
                attempt=attempt,
                failure=failure,
                duration_ms=duration_ms,
            )
        )
        if not failure.recoverable or attempt >= policy.max_attempts:
            return result.model_copy(update={"failure": failure}), attempt, recovered_from
        recovered_from = failure.category

    raise AssertionError("State retry loop exited unexpectedly")
