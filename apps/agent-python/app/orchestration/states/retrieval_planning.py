"""Deterministic construction of bounded, typed retrieval plans."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable
from zoneinfo import ZoneInfoNotFoundError

from app.evidence.knowledge.models import FactType
from app.evidence.retrieval.contracts import RetrievalPlan
from app.orchestration.state_contracts import AgentState, StateContext, StateResult
from app.planning.retrieval_query_builder import RetrievalQueryBuilder
from app.planning.retrieval_time_scope import resolve_as_of
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
        top_k: int = 3,
        request_timezone: str = "Asia/Shanghai",
    ) -> None:
        self._resolve = attraction_resolver
        self._clock = clock or (lambda: datetime.now(UTC))
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive operator-controlled integer")
        self._top_k = min(top_k, 5)
        self._request_timezone = request_timezone
        self._queries = RetrievalQueryBuilder()

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
        if len(resolved) != expected_count or len({item[1] for item in resolved}) != expected_count:
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

        try:
            as_of, require_temporal_coverage = resolve_as_of(
                request, now=self._clock(),
                request_timezone=context.user_context.get("timezone") or self._request_timezone,
            )
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            return StateResult.succeeded(
                next_state=AgentState.CLARIFICATION,
                output={"reason": "invalid_time_scope", "failure_code": "invalid_time_scope",
                        "question": "请提供明确的查询日期（含年份）；时间有歧义时请同时说明时区。"},
            )
        plans = [
            RetrievalPlan(
                task_type=task_type,
                query_text=(
                    f"{name} {request.rewritten_query}" if task_type == "comparison" else request.rewritten_query
                ),
                raw_query=request.raw_query,
                lexical_query=self._queries.from_entity_and_fact_types(name, fact_types),
                user_constraints=request.user_constraints.model_dump(),
                require_explicit_temporal_coverage=require_temporal_coverage,
                attraction_ids=[attraction_id],
                fact_types=fact_types,
                as_of=as_of,
                top_k=self._top_k,
                subtask_id=f"{context.query_id}:{index}:{attraction_id}",
            )
            for index, (name, attraction_id) in enumerate(resolved, start=1)
        ]
        return StateResult.succeeded(
            next_state=AgentState.HYBRID_RETRIEVE,
            output={
                "retrieval_plans": [plan.model_dump(mode="json") for plan in plans],
                "planner": "deterministic-v2",
                "fact_type_whitelist_applied": True,
            },
        )


__all__ = ["RetrievalPlanningHandler"]
