import pytest

from app.agents.information_need_planner import InformationNeedPlanner
from app.agents.query_rewriter import ContextualQueryRewriter
from app.agents.travel_task_extractor import TravelTaskExtractor
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.information_need import InformationNeedType, NeedPriority
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_query import IntentType, UserGoal
from app.tools.tool_router import ToolRouter


def test_query_rewriter_resolves_here_from_context():
    memory = ConversationMemory(last_places=["Kiyomizu-dera"], last_city="Kyoto", last_country="Japan")
    result = ContextualQueryRewriter.rewrite("这里人流量怎么样？", memory)
    assert result.needs_clarification is False
    assert result.resolved_references.get("here") == "Kiyomizu-dera"
    assert "Kiyomizu-dera" in result.rewritten_query
    assert "crowd_level" in result.key_concerns


def test_query_rewriter_asks_when_here_unresolved():
    memory = ConversationMemory()
    result = ContextualQueryRewriter.rewrite("这里人流量怎么样？", memory)
    assert result.needs_clarification is True
    assert result.clarification_prompt
    assert "place_reference" in result.missing_critical_info


def test_travel_task_extracts_crowd_inquiry():
    rewritten = RewrittenQueryResult(
        rewritten_query="Kiyomizu-dera 的人流/拥挤程度",
        resolved_references={"place": "Kiyomizu-dera"},
        key_concerns=["crowd_level"],
        confidence=0.9,
    )
    goal = UserGoal(place_candidates=["Kiyomizu-dera"], destination_city="Kyoto", destination_country="Japan")
    task = TravelTaskExtractor.extract(rewritten, ConversationMemory(), goal)
    assert task.task_type == TravelTaskType.CROWD_INQUIRY
    assert task.places[0].canonical_name == "Kiyomizu-dera"


def test_information_need_planner_for_elderly_suitability():
    task = TravelTask(
        task_type=TravelTaskType.SINGLE_PLACE_SUITABILITY,
        rewritten_query="清水寺适合带爸妈吗",
        places=[],
        key_concerns=["elderly_suitability"],
    )
    needs = InformationNeedPlanner.plan(task)
    types = {n.need_type for n in needs}
    assert InformationNeedType.WALKING_INTENSITY in types
    assert InformationNeedType.ACCESSIBILITY in types
    assert InformationNeedType.CROWD_LEVEL in types
    assert InformationNeedType.TRANSIT in types
    assert any(n.need_type == InformationNeedType.NEARBY_REST_AREA for n in needs)


def test_information_need_planner_for_crowd_query():
    task = TravelTask(
        task_type=TravelTaskType.CROWD_INQUIRY,
        rewritten_query="Kiyomizu-dera crowd",
        key_concerns=["crowd_level"],
    )
    needs = InformationNeedPlanner.plan(task)
    crowd = next(n for n in needs if n.need_type == InformationNeedType.CROWD_LEVEL)
    assert crowd.priority == NeedPriority.HIGH
    assert any(n.need_type == InformationNeedType.QUEUE_TIME for n in needs)


def test_tool_router_maps_crowd_to_review_places_fallback():
    task = TravelTask(
        task_type=TravelTaskType.CROWD_INQUIRY,
        country="Japan",
        city="Kyoto",
        places=[],
    )
    needs = InformationNeedPlanner.plan(task)
    plan = ToolRouter().route(needs, task)
    assert "reviews" in plan.selected_tools
    assert "places" in plan.selected_tools
    assert "fallback" in plan.selected_tools
    assert plan.fallback_used is True
    assert "crowd_level" in plan.estimated_only_needs


def test_tool_router_records_unsupported_need():
    from app.schemas.information_need import InformationNeed

    task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan")
    needs = [
        InformationNeed(
            need_type=InformationNeedType.PHOTO_SPOT,
            priority=NeedPriority.REQUIRED,
            fallback_allowed=False,
        )
    ]
    plan = ToolRouter().route(needs, task)
    assert "photo_spot" in plan.unsupported_needs


@pytest.mark.asyncio
async def test_state_machine_handles_followup_crowd_query():
    sm = TravelAgentStateMachine()
    memory = {
        "conversation_memory": {
            "last_places": ["Kiyomizu-dera"],
            "last_city": "Kyoto",
            "last_country": "Japan",
        }
    }
    resp = await sm.run("这里人流量怎么样？", memory)
    assert resp.answer
    assert not any("请告诉" in resp.answer and "哪个景点" in resp.answer for _ in [0]) or "Kiyomizu" in resp.answer
    assert "Kiyomizu" in resp.answer or "清水寺" in resp.answer or "crowd" in resp.answer.lower()
    assert any("实时" in l or "估算" in l for l in resp.limitations)
    assert any("转写" in t or "改写" in t for t in resp.visible_trace)


@pytest.mark.asyncio
async def test_state_machine_clarifies_unresolved_here():
    sm = TravelAgentStateMachine()
    resp = await sm.run("这里人流量怎么样？")
    assert "景点" in resp.answer or "区域" in resp.answer
    assert resp.confidence < 0.5
    assert any("澄清" in t or "转写" in t or "改写" in t for t in resp.visible_trace)


@pytest.mark.asyncio
async def test_visible_trace_contains_rewrite_and_tool_routing():
    sm = TravelAgentStateMachine()
    resp = await sm.run("故宫今天人多吗？")
    trace_text = " ".join(resp.visible_trace)
    assert "转写" in trace_text or "改写" in trace_text
    assert "信息需求" in trace_text
    assert "工具" in trace_text


@pytest.mark.asyncio
async def test_crowd_answer_disclaims_no_realtime_data():
    sm = TravelAgentStateMachine()
    resp = await sm.run("故宫今天人多吗？")
    combined = resp.answer + " ".join(resp.limitations)
    assert "实时" in combined or "估算" in combined
    assert "Forbidden" in resp.answer or "故宫" in resp.answer or resp.structured_result.places
