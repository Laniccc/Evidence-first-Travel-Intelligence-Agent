"""Deterministic construction of bounded, typed retrieval plans."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

from app.evidence.knowledge.models import FactType
from app.evidence.retrieval.contracts import RetrievalPlan
from app.orchestration.state_contracts import AgentState, StateContext, StateResult
from app.understanding.normalized_user_request import NormalizedUserRequest


_FACT_TYPE_ALIASES = {
    "opening_hours": FactType.OPENING_HOURS,
    "official_hours": FactType.OPENING_HOURS,
    "ticket_price": FactType.TICKET_PRICE,
    "reservation": FactType.RESERVATION,
    "reservation_policy": FactType.RESERVATION,
    "transport": FactType.TRANSPORT,
    "transit": FactType.TRANSPORT,
    "accessibility": FactType.ACCESSIBILITY,
    "walking_intensity": FactType.ACCESSIBILITY,
    "visitor_notice": FactType.VISITOR_NOTICE,
    "crowd_level": FactType.VISITOR_NOTICE,
    "queue_time": FactType.VISITOR_NOTICE,
    "weather": FactType.VISITOR_NOTICE,
    "general_description": FactType.GENERAL_DESCRIPTION,
}
_DEFAULT_FACT_TYPES = {
    "fact_query": [FactType.GENERAL_DESCRIPTION],
    "suitability": [
        FactType.ACCESSIBILITY,
        FactType.VISITOR_NOTICE,
        FactType.GENERAL_DESCRIPTION,
    ],
    "comparison": [
        FactType.ACCESSIBILITY,
        FactType.VISITOR_NOTICE,
        FactType.GENERAL_DESCRIPTION,
    ],
}


class RetrievalPlanningHandler:
    def __init__(
        self,
        *,
        attraction_resolver: Callable[[str], str | None],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._resolve = attraction_resolver
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run(self, context: StateContext) -> StateResult:
        request_raw = context.artifacts.get(AgentState.UNDERSTAND.value, {}).get(
            "normalized_request"
        )
        route = context.artifacts.get(AgentState.ROUTE.value, {})
        if not request_raw or route.get("task_type") not in _DEFAULT_FACT_TYPES:
            return StateResult.succeeded(
                next_state=AgentState.SAFE_FAILURE,
                output={"failure_code": "missing_retrieval_inputs"},
            )

        request = NormalizedUserRequest.model_validate(request_raw)
        names = route.get("attraction_names") or [
            entity.normalized_name or entity.text
            for entity in request.entities
            if entity.entity_type in {"attraction", "landmark", "natural_site"}
        ]
        resolved: list[tuple[str, str]] = []
        for name in names:
            try:
                attraction_id = self._resolve(name)
            except (KeyError, LookupError, ValueError):
                attraction_id = None
            if not attraction_id:
                return StateResult.succeeded(
                    next_state=AgentState.CLARIFICATION,
                    output={
                        "reason": "unresolved_attraction",
                        "attraction_name": name,
                        "question": f"无法确认“{name}”对应的景点，请提供更完整名称。",
                    },
                )
            resolved.append((name, attraction_id))

        task_type = route["task_type"]
        expected_count = 2 if task_type == "comparison" else 1
        if len(resolved) != expected_count:
            return StateResult.succeeded(
                next_state=AgentState.CLARIFICATION,
                output={"reason": "invalid_attraction_count", "expected": expected_count},
            )

        fact_types = []
        for need in request.information_needs:
            fact_type = _FACT_TYPE_ALIASES.get(need.need_type)
            if fact_type and fact_type not in fact_types:
                fact_types.append(fact_type)
        if not fact_types:
            decision_fact = _FACT_TYPE_ALIASES.get(request.decision_type)
            fact_types = [decision_fact] if decision_fact else list(_DEFAULT_FACT_TYPES[task_type])

        as_of = self._clock()
        plans = [
            RetrievalPlan(
                task_type=task_type,
                query_text=(
                    f"{name} {request.rewritten_query}" if task_type == "comparison" else request.rewritten_query
                ),
                attraction_ids=[attraction_id],
                fact_types=fact_types,
                as_of=as_of,
                top_k=3,
                subtask_id=f"{context.query_id}:{index}:{attraction_id}",
            )
            for index, (name, attraction_id) in enumerate(resolved, start=1)
        ]
        return StateResult.succeeded(
            next_state=AgentState.HYBRID_RETRIEVE,
            output={
                "retrieval_plans": [plan.model_dump(mode="json") for plan in plans],
                "planner": "deterministic-v1",
                "fact_type_whitelist_applied": True,
            },
        )


__all__ = ["RetrievalPlanningHandler"]
