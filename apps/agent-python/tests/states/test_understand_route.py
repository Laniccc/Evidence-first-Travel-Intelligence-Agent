import pytest

from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.llm_understanding import UnderstandingHandler
from app.orchestration.states.routing import RouteHandler, RoutedTaskHandler
from app.orchestration.transition_table import is_allowed_transition
from app.understanding.normalized_user_request import NormalizedEntity, NormalizedUserRequest
from app.evidence.knowledge.models import Attraction


def context(query: str = "故宫开放时间") -> StateContext:
    return StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query=query,
        artifacts={
            "context": {
                "snapshot": {
                    "session": {"query": query, "session_id": "session-1", "user_context": {}},
                    "conversation_context": {},
                }
            }
        },
    )


def normalized(task_family: str, names=("故宫博物院",)) -> NormalizedUserRequest:
    return NormalizedUserRequest(
        raw_query="test",
        rewritten_query="test",
        query_scope="place",
        task_family=task_family,
        entities=[
            NormalizedEntity(text=name, normalized_name=name, entity_type="attraction")
            for name in names
        ],
        confidence=0.9,
    )


class AlwaysInvalidPrimary:
    def __init__(self):
        self.repairs = []

    async def normalize(self, raw_query, conversation_context, *, repair):
        self.repairs.append(repair)
        raise ValueError("malformed model payload")


@pytest.mark.asyncio
async def test_understand_repairs_once_then_uses_rule_fallback():
    primary = AlwaysInvalidPrimary()
    handler = UnderstandingHandler(
        primary=primary,
        rule_fallback=lambda *_: normalized("fact_lookup"),
    )

    result = await handler.run(context())

    assert primary.repairs == [False, True]
    assert result.status == "recovered"
    assert result.recovery.strategy == "rule_fallback"
    assert result.next_state is AgentState.ROUTE
    assert result.output["understanding_attempts"] == ["model", "repair", "rule"]


@pytest.mark.asyncio
async def test_rule_fallback_can_use_governed_attraction_catalog():
    fallback = normalized("unknown", names=())
    handler = UnderstandingHandler(
        rule_fallback=lambda *_: fallback,
        attraction_matcher=lambda _: [
            Attraction(attraction_id="forbidden-city", name="故宫博物院")
        ],
    )

    result = await handler.run(context("故宫开放时间"))

    request = NormalizedUserRequest.model_validate(result.output["normalized_request"])
    assert request.task_family == "fact_lookup"
    assert [entity.normalized_name for entity in request.entities] == ["故宫博物院"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_family", "names", "expected"),
    [
        ("fact_lookup", ("故宫博物院",), AgentState.FACT_QUERY),
        ("suitability", ("故宫博物院",), AgentState.SUITABILITY),
        ("comparison", ("故宫博物院", "颐和园"), AgentState.COMPARISON),
    ],
)
async def test_route_allows_only_supported_tasks(task_family, names, expected):
    state = context()
    state.artifacts["understand"] = {
        "normalized_request": normalized(task_family, names).model_dump(mode="json")
    }

    result = await RouteHandler().run(state)

    assert result.next_state is expected
    marker = await RoutedTaskHandler(expected).run(
        state.model_copy(update={"artifacts": {**state.artifacts, "route": result.output}})
    )
    assert marker.next_state is AgentState.RETRIEVAL_PLAN


@pytest.mark.asyncio
async def test_route_sends_pruned_task_to_clarification():
    state = context("帮我安排故宫一日游")
    state.artifacts["understand"] = {
        "normalized_request": normalized("planning").model_dump(mode="json")
    }

    result = await RouteHandler().run(state)

    assert result.next_state is AgentState.CLARIFICATION
    assert result.output["reason"] == "unsupported_task"


def test_supported_main_path_uses_explicit_retrieval_plan_and_hybrid_states():
    path = [
        AgentState.INGRESS,
        AgentState.CONTEXT,
        AgentState.UNDERSTAND,
        AgentState.ROUTE,
        AgentState.FACT_QUERY,
        AgentState.RETRIEVAL_PLAN,
        AgentState.HYBRID_RETRIEVE,
    ]

    assert all(is_allowed_transition(left, right) for left, right in zip(path, path[1:]))
    assert "rag_retrieve" not in {state.value for state in AgentState}
