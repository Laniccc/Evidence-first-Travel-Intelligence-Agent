"""Deterministic executor for the explicit Evidence-first Agent state chain."""

from __future__ import annotations

from app.orchestration.state_execution import execute_state_handler
from app.orchestration.state_audit import StateAuditEvent, StateAuditStore
from app.orchestration.state_contracts import (
    AgentState,
    FailureClass,
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
        return await execute_state_handler(context, state, handler, policy, self.audit)
