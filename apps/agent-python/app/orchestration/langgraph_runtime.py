"""LangGraph schedules existing typed handlers; it owns no business policy."""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.orchestration.state_audit import StateAuditEvent, StateAuditStore
from app.orchestration.state_contracts import (
    AgentState, FailureClass, StateContext, StateFailure, StateHandler,
    StatePolicy, StateRunResult, TERMINAL_STATES,
)
from app.orchestration.state_execution import execute_state_handler
from app.orchestration.transition_table import ALLOWED_TRANSITIONS, is_allowed_transition


class LangGraphState(TypedDict):
    # "context" is already a business node name. Keep the same object, not a copy.
    run_context: StateContext
    next_state: str
    terminal_state: str | None
    failure: StateFailure | None
    steps: int


def _route(state: LangGraphState) -> str:
    return state["next_state"]


class LangGraphRuntime:
    def __init__(self, *, handlers: dict[AgentState, StateHandler], audit: StateAuditStore,
                 policies: dict[AgentState, StatePolicy] | None = None, max_steps: int = 24):
        self.handlers, self.audit = handlers, audit
        self.policies, self.max_steps = policies or {}, max_steps
        builder = StateGraph(LangGraphState)
        for state in AgentState:
            if state not in TERMINAL_STATES:
                builder.add_node(state.value, self._node(state))
                builder.add_conditional_edges(state.value, _route, {
                    target.value: END if target in TERMINAL_STATES else target.value
                    for target in ALLOWED_TRANSITIONS[state]
                })
        builder.add_conditional_edges(START, _route, {
            state.value: END if state in TERMINAL_STATES else state.value for state in AgentState
        })
        self.graph = builder.compile()

    def _node(self, current: AgentState):
        async def invoke(state: LangGraphState):
            context, steps = state["run_context"], state["steps"]
            if steps >= self.max_steps:
                return self._failed(context, current, steps, StateFailure(
                    category=FailureClass.BUDGET_EXHAUSTED, code="max_steps_exceeded",
                    message=f"State runtime exceeded {self.max_steps} steps", recoverable=False))
            handler = self.handlers.get(current)
            if handler is None:
                return self._failed(context, current, steps, StateFailure(
                    category=FailureClass.DEPENDENCY_UNAVAILABLE, code="missing_state_handler",
                    message=f"No handler registered for {current.value}", recoverable=False))
            context.current_state = current
            result, attempt, _ = await execute_state_handler(
                context, current, handler, self.policies.get(current, StatePolicy()), self.audit)
            if result.status == "failed":
                # The shared executor already wrote the failure audit.
                return {"next_state": AgentState.FAILED.value, "terminal_state": AgentState.FAILED.value,
                        "failure": result.failure, "steps": steps + 1}
            if not is_allowed_transition(current, result.next_state):
                return self._failed(context, current, steps + 1, StateFailure(
                    category=FailureClass.ILLEGAL_TRANSITION, code="illegal_transition",
                    message=f"Illegal transition {current.value} -> {result.next_state.value}",
                    recoverable=False, details={"from": current.value, "to": result.next_state.value}),
                    attempt=attempt)
            # Commit only after transition validation, in the original audit order.
            context.artifacts[current.value] = result.output
            self.audit.append(StateAuditEvent.transition(context, from_state=current,
                                                        to_state=result.next_state, attempt=attempt))
            terminal = result.next_state in TERMINAL_STATES
            if terminal:
                context.current_state = result.next_state
            return {"run_context": context, "next_state": result.next_state.value, "steps": steps + 1,
                    "terminal_state": result.next_state.value if terminal else None, "failure": None}
        return invoke

    def _failed(self, context, current, steps, failure, *, attempt=1):
        self.audit.append(StateAuditEvent.failed(context, current, attempt=attempt, failure=failure))
        return {"next_state": AgentState.FAILED.value, "terminal_state": AgentState.FAILED.value,
                "failure": failure, "steps": steps}

    async def run(self, context: StateContext) -> StateRunResult:
        initial: LangGraphState = {
            "run_context": context, "next_state": context.current_state.value,
            "terminal_state": context.current_state.value if context.current_state in TERMINAL_STATES else None,
            "failure": None, "steps": 0,
        }
        # Leave one extra node to emit the existing typed budget failure before
        # LangGraph's emergency recursion limit. No second workflow loop/retry.
        outcome = await self.graph.ainvoke(initial, config={"recursion_limit": max(0, self.max_steps) + 2})
        return StateRunResult(terminal_state=AgentState(outcome["terminal_state"]), context=context,
                              failure=outcome["failure"], steps=outcome["steps"])
