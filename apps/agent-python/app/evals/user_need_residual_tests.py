"""Tests for S2 user-need residual isolation."""

import json

from app.orchestrator.user_need_residual import build_user_need_residual
from app.schemas.semantic_frame import DecisionType, QueryScope, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def _frame_with_entities() -> SemanticFrame:
    return SemanticFrame(
        raw_query="巴音布鲁克景区门票价格",
        normalized_request="查询景区门票价格",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(
            country="中国",
            city="巴音",
            places=["巴音布鲁克景区"],
        ),
        information_needs=["ticket_price", "opening_hours"],
        user_constraints=["带老人"],
        requires_exact_fact=True,
        key_concerns=["门票多少钱"],
    )


def test_residual_excludes_raw_query_and_entities():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="巴音布鲁克门票65元对吗",
        semantic_frame=_frame_with_entities(),
    )
    residual = build_user_need_residual(state)
    payload = residual.model_dump()
    blob = json.dumps(payload, ensure_ascii=False)
    assert "巴音布鲁克门票65元" not in blob
    assert "巴音布鲁克景区" not in blob
    assert "巴音" not in blob
    assert residual.requires_exact_fact is True
    assert any(n.need_type == "ticket_price" for n in residual.information_needs)


def test_residual_includes_needs_and_constraints_not_places():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="南京博物院适合父母吗",
        semantic_frame=SemanticFrame(
            raw_query="南京博物院适合父母吗",
            normalized_request="评估是否适合带父母游览",
            task_family=TaskFamily.SUITABILITY,
            decision_type=DecisionType.WHETHER_TO_GO,
            entities=SemanticEntities(places=["南京博物院"], city="南京"),
            information_needs=["crowd_level", "accessibility"],
            user_constraints=["父母", "慢节奏"],
        ),
    )
    residual = build_user_need_residual(state)
    assert residual.task_family == "suitability"
    assert "父母" in json.dumps(residual.user_constraints.model_dump(), ensure_ascii=False)
    assert "南京博物院" not in json.dumps(residual.model_dump(), ensure_ascii=False)


def test_attach_residual_on_state():
    from app.orchestrator.user_need_residual import attach_user_need_residual

    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="test",
        semantic_frame=_frame_with_entities(),
    )
    attach_user_need_residual(state)
    assert state.user_need_residual is not None
    assert state.user_need_residual.intent_summary
