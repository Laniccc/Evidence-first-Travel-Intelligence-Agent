"""Deterministic product-scope routing for the three supported tasks."""

from __future__ import annotations

from app.orchestration.state_contracts import AgentState, StateContext, StateResult
from app.understanding.normalized_user_request import NormalizedUserRequest


_TASK_TO_STATE = {
    "fact_lookup": AgentState.FACT_QUERY,
    "suitability": AgentState.SUITABILITY,
    "comparison": AgentState.COMPARISON,
}
_STATE_TO_TASK = {
    AgentState.FACT_QUERY: "fact_query",
    AgentState.SUITABILITY: "suitability",
    AgentState.COMPARISON: "comparison",
}


def _attraction_names(request: NormalizedUserRequest) -> list[str]:
    names = []
    for entity in request.entities:
        if entity.entity_type not in {"attraction", "landmark", "natural_site"}:
            continue
        name = entity.normalized_name or entity.text
        if name and name not in names:
            names.append(name)
    return names


class RouteHandler:
    async def run(self, context: StateContext) -> StateResult:
        raw = context.artifacts.get(AgentState.UNDERSTAND.value, {}).get("normalized_request")
        if not raw:
            return StateResult.succeeded(
                next_state=AgentState.CLARIFICATION,
                output={"reason": "missing_understanding", "question": "请说明要查询的景点。"},
            )
        request = NormalizedUserRequest.model_validate(raw)
        next_state = _TASK_TO_STATE.get(request.task_family)
        if next_state is None:
            return StateResult.succeeded(
                next_state=AgentState.CLARIFICATION,
                output={
                    "reason": "unsupported_task",
                    "requested_task": request.task_family,
                    "question": "目前支持景点事实、适合度和两个景点的比较，请换一种问法。",
                },
            )

        names = _attraction_names(request)
        expected_count = 2 if next_state is AgentState.COMPARISON else 1
        if len(names) != expected_count:
            return StateResult.succeeded(
                next_state=AgentState.CLARIFICATION,
                output={
                    "reason": "invalid_attraction_count",
                    "expected": expected_count,
                    "actual": len(names),
                    "question": "请明确要查询的景点" + ("（恰好两个）" if expected_count == 2 else ""),
                },
            )

        return StateResult.succeeded(
            next_state=next_state,
            output={
                "task_type": _STATE_TO_TASK[next_state],
                "attraction_names": names,
            },
        )


class RoutedTaskHandler:
    """Auditable branch marker before the shared retrieval-planning state."""

    def __init__(self, state: AgentState) -> None:
        if state not in _STATE_TO_TASK:
            raise ValueError(f"unsupported routed state: {state}")
        self._state = state

    async def run(self, context: StateContext) -> StateResult:
        route = context.artifacts.get(AgentState.ROUTE.value, {})
        expected = _STATE_TO_TASK[self._state]
        if route.get("task_type") != expected:
            return StateResult.succeeded(
                next_state=AgentState.SAFE_FAILURE,
                output={"failure_code": "route_artifact_mismatch", "expected": expected},
            )
        return StateResult.succeeded(
            next_state=AgentState.RETRIEVAL_PLAN,
            output={"task_type": expected, "route_validated": True},
        )


__all__ = ["RouteHandler", "RoutedTaskHandler"]
