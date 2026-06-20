import re
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.conversation_context_builder import ConversationContextBuilder
from app.agents.query_understanding_agent import QueryUnderstandingAgent
from app.agents.rule_based_understanding import RuleBasedUnderstanding
from app.llm_client import LLMClient
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.conversation_context import ConversationContext
from app.schemas.travel_task import TravelTaskType
from app.schemas.user_query import TravelAgentState


def _assert_no_facts(result) -> None:
    fields = " ".join(
        [
            result.rewritten_query,
            result.clarification_question or "",
            " ".join(result.assumptions),
        ]
    )
    forbidden = [r"\d{1,2}:\d{2}", r"\d+\s*(?:JPY|CNY|KRW|元)", r"天气[:：]\s*", r"开放时间[:：]"]
    for pattern in forbidden:
        assert not re.search(pattern, fields), f"Unexpected fact-like pattern in understanding output: {pattern}"


def test_query_understanding_single_place_elderly():
    ctx = ConversationContext()
    result = RuleBasedUnderstanding.understand("京都清水寺适合带父母去吗？", ctx)
    assert result.needs_clarification is False
    assert result.travel_task.task_type == TravelTaskType.SINGLE_PLACE_SUITABILITY
    assert result.travel_task.country == "Japan"
    assert result.travel_task.city == "Kyoto"
    assert any(p.canonical_name == "Kiyomizu-dera" for p in result.travel_task.places)
    assert "elderly" in (result.travel_task.user_profile.party if result.travel_task.user_profile else [])
    assert "walking_intensity" in result.travel_task.key_concerns
    _assert_no_facts(result)


def test_query_understanding_resolves_here_from_context():
    ctx = ConversationContext(
        last_places=[
            {
                "original_name": "Kiyomizu-dera",
                "canonical_name": "Kiyomizu-dera",
                "country": "Japan",
                "city": "Kyoto",
                "confidence": 0.95,
                "source": "query_understanding",
            }
        ],
        last_city="Kyoto",
        last_country="Japan",
    )
    result = RuleBasedUnderstanding.understand("这里人流量怎么样？", ctx)
    assert result.needs_clarification is False
    assert result.resolved_references.get("here") == "Kiyomizu-dera"
    assert result.travel_task.task_type == TravelTaskType.CROWD_INQUIRY
    assert "crowd_level" in result.travel_task.key_concerns
    _assert_no_facts(result)


def test_query_understanding_clarifies_unresolved_here():
    result = RuleBasedUnderstanding.understand("这里人流量怎么样？", ConversationContext())
    assert result.needs_clarification is True
    assert result.clarification_question
    assert "place_reference" in result.missing_critical_info


def test_query_understanding_followup_tomorrow():
    builder = ConversationContextBuilder()
    state = TravelAgentState(session_id="t", query_id="q", raw_user_query="那明天呢？")
    ctx = builder.build(
        state,
        {
            "conversation_context": {
                "last_places": ["Forbidden City"],
                "last_country": "China",
                "last_city": "Beijing",
                "last_task_type": "place_fact_lookup",
            }
        },
    )
    result = RuleBasedUnderstanding.understand("那明天呢？", ctx)
    assert result.travel_task.followup_context_used is True
    assert result.travel_task.places[0].canonical_name == "Forbidden City"
    assert result.travel_task.travel_date == "tomorrow"
    _assert_no_facts(result)


def test_query_understanding_no_fact_generation():
    QueryUnderstandingAgent(LLMClient())
    result = RuleBasedUnderstanding.understand("故宫今天人多吗？", ConversationContext())
    _assert_no_facts(result)


@pytest.mark.asyncio
async def test_state_machine_stops_on_clarification():
    sm = TravelAgentStateMachine()
    resp = await sm.run("这里人流量怎么样？")
    assert resp.confidence < 0.5
    assert len(resp.tool_traces) == 0
    assert len(resp.evidence_summary) == 0
    assert "景点" in resp.answer or "区域" in resp.answer
    trace = " ".join(resp.visible_trace)
    assert "转写" in trace or "会话上下文" in trace


@pytest.mark.asyncio
async def test_visible_trace_contains_query_understanding():
    sm = TravelAgentStateMachine()
    resp = await sm.run("京都清水寺适合带父母去吗？", {"party": ["elderly"]})
    trace = " ".join(resp.visible_trace)
    assert "会话上下文" in trace or "构建" in trace
    assert "转写" in trace
    assert "TravelTask" in trace


@pytest.mark.asyncio
async def test_state_machine_uses_travel_task_not_intent_agent():
    sm = TravelAgentStateMachine()
    with patch("app.agents.intent_agent.IntentAgent.run", new_callable=AsyncMock) as intent_mock:
        intent_mock.side_effect = RuntimeError("IntentAgent should not be called")
        resp = await sm.run("京都清水寺适合带父母去吗？", {"party": ["elderly"]})
    assert resp.answer
    assert "TravelTask" in " ".join(resp.visible_trace)
    intent_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_clarification_does_not_call_tools():
    sm = TravelAgentStateMachine()

    async def boom(*args, **kwargs):
        raise RuntimeError("tools must not run on clarification")

    with patch.object(sm.tools, "run_tool", side_effect=boom):
        resp = await sm.run("这里人流量怎么样？")
    assert len(resp.tool_traces) == 0
    assert len(resp.evidence_summary) == 0
