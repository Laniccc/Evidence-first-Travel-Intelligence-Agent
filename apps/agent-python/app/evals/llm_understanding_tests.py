import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.agents.llm_understanding_agent import LLMUnderstandingSubAgent
from app.agents.normalized_request_to_semantic_frame import NormalizedRequestToSemanticFrame
from app.agents.rule_based_understanding import RuleBasedUnderstanding
from app.orchestrator.answer_mode_router import AnswerModeRouter
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.conversation_context import ConversationContext
from app.schemas.normalized_user_request import (
    AnswerPolicyDraft,
    InformationNeedDraft,
    NormalizedEntity,
    NormalizedTimeScope,
    NormalizedUserConstraints,
    NormalizedUserRequest,
)
from app.schemas.place_context import PlaceContext
from app.schemas.semantic_frame import AnswerMode
from app.schemas.user_query import TravelAgentState
from app.tools.knowledge_prior_tool import KnowledgePriorTool


def _kanas_best_month_request() -> NormalizedUserRequest:
    return NormalizedUserRequest(
        raw_query="喀纳斯湖适合几月份去",
        rewritten_query="喀纳斯湖适合几月份去？（最佳季节建议）",
        intent_summary="询问喀纳斯湖最佳出行月份",
        query_scope="place",
        task_family="advisory",
        decision_type="best_time_to_visit",
        entities=[
            NormalizedEntity(
                text="喀纳斯湖",
                normalized_name="喀纳斯湖",
                entity_type="natural_site",
                country="China",
                region="新疆",
                source="llm_understanding",
                confidence=0.85,
            )
        ],
        time_scope=NormalizedTimeScope(scope="seasonal"),
        information_needs=[
            InformationNeedDraft(need_type="best_time_to_visit", priority="high"),
            InformationNeedDraft(need_type="seasonality", priority="medium"),
        ],
        answer_policy=AnswerPolicyDraft(
            requires_live_data=False,
            requires_exact_fact=False,
            can_answer_with_model_prior=True,
        ),
        confidence=0.88,
    )


def _kanas_opening_hours_request() -> NormalizedUserRequest:
    return NormalizedUserRequest(
        raw_query="喀纳斯湖今天几点开放",
        rewritten_query="喀纳斯湖今天的开放时间",
        intent_summary="查询喀纳斯湖今日开放时间",
        query_scope="place",
        task_family="fact_lookup",
        decision_type="opening_hours",
        entities=[
            NormalizedEntity(
                text="喀纳斯湖",
                normalized_name="喀纳斯湖",
                entity_type="natural_site",
                country="China",
                confidence=0.9,
            )
        ],
        time_scope=NormalizedTimeScope(scope="current"),
        information_needs=[InformationNeedDraft(need_type="opening_hours", priority="required")],
        answer_policy=AnswerPolicyDraft(
            requires_live_data=False,
            requires_exact_fact=True,
            can_answer_with_model_prior=False,
        ),
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_llm_understanding_kanas_best_month():
    agent = LLMUnderstandingSubAgent(MagicMock())
    with patch.object(agent, "_call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = json.dumps(_kanas_best_month_request().model_dump(), ensure_ascii=False)
        result = await agent.run("喀纳斯湖适合几月份去", ConversationContext())

    assert result.decision_type == "best_time_to_visit"
    assert result.task_family == "advisory"
    assert any("喀纳斯湖" in (e.text or "") for e in result.entities)
    assert result.entities[0].entity_type in {"natural_site", "attraction", "landmark", "region", "place"}
    assert result.answer_policy.can_answer_with_model_prior is True
    assert result.needs_clarification is False


@pytest.mark.asyncio
async def test_kanas_not_blocked_by_place_registry(monkeypatch):
    monkeypatch.setattr(
        "app.tools.mock.data.PLACE_REGISTRY",
        {},
        raising=False,
    )
    frame = NormalizedRequestToSemanticFrame.convert(_kanas_best_month_request())
    decision = AnswerModeRouter().route(frame, available_capabilities=set())
    assert decision.answer_mode == AnswerMode.MODEL_PRIOR_ALLOWED
    assert decision.allow_knowledge_prior is True


def test_kanas_region_propagates_to_semantic_frame():
    frame = NormalizedRequestToSemanticFrame.convert(_kanas_best_month_request())
    assert frame.entities.region == "新疆"


@pytest.mark.asyncio
async def test_kanas_state_machine_answers_with_model_prior():
    sm = TravelAgentStateMachine()
    kanas = _kanas_best_month_request()
    with patch.object(
        sm.llm_understanding_state.agent,
        "run",
        new_callable=AsyncMock,
        return_value=kanas,
    ):
        resp = await sm.run("喀纳斯湖适合几月份去")

    assert resp.answer_mode == "model_prior_allowed"
    assert "请提供" not in (resp.answer or "")
    assert "具体景点" not in (resp.answer or "")
    assert any(
        t.get("tool_name") == "knowledge_prior" or "model prior" in str(t).lower()
        for t in resp.tool_traces
    ) or any("常识" in lim or "季节" in lim for lim in resp.limitations)


@pytest.mark.asyncio
async def test_opening_hours_not_model_prior():
    frame = NormalizedRequestToSemanticFrame.convert(_kanas_opening_hours_request())
    decision = AnswerModeRouter().route(frame, available_capabilities=set())
    assert frame.requires_exact_fact is True
    assert frame.can_answer_with_model_prior is False
    assert decision.allow_knowledge_prior is False
    assert decision.answer_mode == AnswerMode.EVIDENCE_REQUIRED

    tool = KnowledgePriorTool()
    with pytest.raises(ValueError, match="cannot generate claim"):
        await tool.run(
            raw_query="喀纳斯湖今天几点开放",
            semantic_frame=frame,
        )


@pytest.mark.asyncio
async def test_deictic_here_requires_context():
    agent = LLMUnderstandingSubAgent(MagicMock())
    payload = _kanas_best_month_request().model_dump()
    payload["raw_query"] = "这里适合几月份去"
    payload["rewritten_query"] = "这里适合几月份去"
    payload["entities"] = []
    payload["needs_clarification"] = True
    payload["clarification_question"] = "你指的是哪个地点？"
    payload["missing_critical_info"] = ["place_reference"]

    with patch.object(agent, "_call_llm", new_callable=AsyncMock, return_value=json.dumps(payload, ensure_ascii=False)):
        result = await agent.run("这里适合几月份去", ConversationContext())

    assert result.needs_clarification is True
    assert result.clarification_question


@pytest.mark.asyncio
async def test_deictic_here_uses_context():
    agent = LLMUnderstandingSubAgent(MagicMock())
    ctx = ConversationContext(
        last_places=[
            PlaceContext(
                original_name="喀纳斯湖",
                canonical_name="喀纳斯湖",
                country="China",
                city="阿勒泰",
            )
        ],
        last_country="China",
        last_city="阿勒泰",
    )
    payload = _kanas_best_month_request().model_dump()
    payload["raw_query"] = "这里适合几月份去"
    payload["rewritten_query"] = "喀纳斯湖适合几月份去"
    payload["entities"][0]["source"] = "conversation_context"

    with patch.object(agent, "_call_llm", new_callable=AsyncMock, return_value=json.dumps(payload, ensure_ascii=False)):
        result = await agent.run("这里适合几月份去", ctx)

    assert result.needs_clarification is False
    assert any("喀纳斯" in (e.text or e.normalized_name or "") for e in result.entities)


@pytest.mark.asyncio
async def test_normalized_json_repair():
    agent = LLMUnderstandingSubAgent(MagicMock())
    valid = json.dumps(_kanas_best_month_request().model_dump(), ensure_ascii=False)

    async def fake_llm(raw_query, conversation_context, supported_regions):
        if fake_llm.calls == 0:
            fake_llm.calls += 1
            return "{ invalid json"
        return valid

    fake_llm.calls = 0

    with patch.object(agent, "_call_llm", side_effect=fake_llm):
        with patch.object(agent.llm, "complete", new_callable=AsyncMock, return_value=valid):
            result = await agent._run_with_repair("喀纳斯湖适合几月份去", ConversationContext(), ["China"])

    assert result.decision_type == "best_time_to_visit"


@pytest.mark.asyncio
async def test_rule_based_fallback_only_when_llm_unavailable(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    from app.config import get_settings

    get_settings.cache_clear()
    agent = LLMUnderstandingSubAgent()
    assert agent.llm._should_use_anthropic() is False

    with patch.object(RuleBasedUnderstanding, "understand") as mock_rule:
        mock_rule.return_value = RuleBasedUnderstanding._clarification(
            "测试",
            [],
            "clarify",
            ["place_reference"],
        )
        result = await agent.run("测试", ConversationContext())
        mock_rule.assert_called_once()
        assert result.needs_clarification is True


def test_s3_contract_compliant_kanas_routes_model_prior():
    """Payload matches llm_understanding.system.md example A — S3 must accept without adapter inference."""
    req = NormalizedUserRequest(
        raw_query="喀纳斯湖适合几月份去",
        rewritten_query="喀纳斯湖的最佳出行月份与季节建议",
        query_scope="place",
        task_family="advisory",
        decision_type="best_time_to_visit",
        entities=[
            NormalizedEntity(
                text="喀纳斯湖",
                normalized_name="喀纳斯湖",
                entity_type="natural_site",
                country="China",
                region="新疆",
                city="Altay",
                confidence=0.88,
            )
        ],
        time_scope=NormalizedTimeScope(scope="seasonal"),
        information_needs=[
            InformationNeedDraft(need_type="best_time_to_visit", priority="high"),
            InformationNeedDraft(need_type="seasonality", priority="medium"),
        ],
        answer_policy=AnswerPolicyDraft(
            requires_exact_fact=False,
            requires_live_data=False,
            can_answer_with_model_prior=True,
        ),
        confidence=0.88,
    )
    frame = NormalizedRequestToSemanticFrame.convert(req)
    assert frame.query_scope.value == "place"
    assert frame.entities.country == "China"
    assert frame.can_answer_with_model_prior is True
    decision = AnswerModeRouter().route(frame, available_capabilities=set())
    assert decision.answer_mode == AnswerMode.MODEL_PRIOR_ALLOWED


def test_prompt_files_define_s3_contract():
    from pathlib import Path

    prompts = Path(__file__).resolve().parents[1] / "prompts"
    system = (prompts / "llm_understanding.system.md").read_text(encoding="utf-8")
    contract = (prompts / "llm_understanding.routing_contract.md").read_text(encoding="utf-8")
    user = (prompts / "llm_understanding.user.md").read_text(encoding="utf-8")
    assert "{{routing_contract}}" in system
    assert "model_prior_allowed" in contract
    assert "禁止" in contract and "name" in contract
    assert "query_scope" in contract
    assert "自检" in user
    assert "NormalizedUserRequest" in user
