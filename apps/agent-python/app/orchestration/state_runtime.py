"""Deterministic executor for the explicit Evidence-first Agent state chain."""

from __future__ import annotations

import asyncio
import time

from app.orchestration.state_audit import StateAuditEvent, StateAuditStore
from app.orchestration.state_contracts import (
    AgentState,
    FailureClass,
    RecoveryRecord,
    StateContext,
    StateFailure,
    StateHandler,
    StatePolicy,
    StateResult,
    StateRunResult,
    TERMINAL_STATES,
)
from app.orchestration.transition_table import is_allowed_transition


class StateRuntime:
    def __init__(
        self,
        *,
        handlers: dict[AgentState, StateHandler],
        audit: StateAuditStore,
        policies: dict[AgentState, StatePolicy] | None = None,
        max_steps: int = 24,
    ) -> None:
        self.handlers = handlers
        self.audit = audit
        self.policies = policies or {}
        self.max_steps = max_steps

    async def run(self, context: StateContext) -> StateRunResult:
        state = context.current_state
        steps = 0

        while state not in TERMINAL_STATES:
            if steps >= self.max_steps:
                failure = StateFailure(
                    category=FailureClass.BUDGET_EXHAUSTED,
                    code="max_steps_exceeded",
                    message=f"State runtime exceeded {self.max_steps} steps",
                    recoverable=False,
                )
                self.audit.append(
                    StateAuditEvent.failed(
                        context,
                        state,
                        attempt=1,
                        failure=failure,
                    )
                )
                return StateRunResult(
                    terminal_state=AgentState.FAILED,
                    context=context,
                    failure=failure,
                    steps=steps,
                )

            handler = self.handlers.get(state)
            if handler is None:
                failure = StateFailure(
                    category=FailureClass.DEPENDENCY_UNAVAILABLE,
                    code="missing_state_handler",
                    message=f"No handler registered for {state.value}",
                    recoverable=False,
                )
                self.audit.append(
                    StateAuditEvent.failed(context, state, attempt=1, failure=failure)
                )
                return StateRunResult(
                    terminal_state=AgentState.FAILED,
                    context=context,
                    failure=failure,
                    steps=steps,
                )

            context.current_state = state
            policy = self.policies.get(state, StatePolicy())
            result, attempt, recovered_from = await self._run_handler(
                context,
                state,
                handler,
                policy,
            )
            if result.status == "failed":
                return StateRunResult(
                    terminal_state=AgentState.FAILED,
                    context=context,
                    failure=result.failure,
                    steps=steps + 1,
                )

            if not is_allowed_transition(state, result.next_state):
                failure = StateFailure(
                    category=FailureClass.ILLEGAL_TRANSITION,
                    code="illegal_transition",
                    message=f"Illegal transition {state.value} -> {result.next_state.value}",
                    recoverable=False,
                    details={"from": state.value, "to": result.next_state.value},
                )
                self.audit.append(
                    StateAuditEvent.failed(
                        context,
                        state,
                        attempt=attempt,
                        failure=failure,
                    )
                )
                return StateRunResult(
                    terminal_state=AgentState.FAILED,
                    context=context,
                    failure=failure,
                    steps=steps + 1,
                )

            context.artifacts[state.value] = result.output
            self.audit.append(
                StateAuditEvent.transition(
                    context,
                    from_state=state,
                    to_state=result.next_state,
                    attempt=attempt,
                )
            )
            state = result.next_state
            steps += 1

        context.current_state = state
        return StateRunResult(
            terminal_state=state,
            context=context,
            steps=steps,
        )

    async def _run_handler(
        self,
        context: StateContext,
        state: AgentState,
        handler: StateHandler,
        policy: StatePolicy,
    ) -> tuple[StateResult, int, FailureClass | None]:
        recovered_from: FailureClass | None = None
        for attempt in range(1, policy.max_attempts + 1):
            self.audit.append(StateAuditEvent.started(context, state, attempt=attempt))
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
                self.audit.append(
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
            self.audit.append(
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
