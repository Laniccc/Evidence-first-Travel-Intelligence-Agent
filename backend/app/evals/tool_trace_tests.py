import inspect
import re
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.place_research_agent import PlaceResearchAgent
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.place_context import PlaceContext
from app.schemas.user_query import UserGoal
from app.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_place_research_uses_run_tool_for_tracing():
    tools = ToolRegistry()
    agent = PlaceResearchAgent(tools)
    goal = UserGoal(
        place_candidates=["Kiyomizu-dera"],
        destination_city="Kyoto",
        destination_country="Japan",
    )

    with patch.object(tools, "run_tool", new_callable=AsyncMock) as run_mock:
        run_mock.return_value = []
        await agent.retrieve_for_place("Kiyomizu-dera", goal, ["official", "places"])
        assert run_mock.await_count >= 2
        assert all(call.args[0] in {"official", "places"} for call in run_mock.await_args_list)


@pytest.mark.asyncio
async def test_tool_trace_records_evidence_ids():
    tools = ToolRegistry()
    await tools.run_tool("official", place_name="Kiyomizu-dera")
    trace = tools.traces[-1]
    assert trace.tool_name == "official"
    assert trace.status == "ok"
    assert trace.evidence_ids
    assert trace.latency_ms >= 0


@pytest.mark.asyncio
async def test_tool_trace_records_error_for_missing_tool():
    tools = ToolRegistry()
    await tools.run_tool("nonexistent_tool_xyz", place_name="Kiyomizu-dera")
    trace = tools.traces[-1]
    assert trace.tool_name == "nonexistent_tool_xyz"
    assert trace.status == "error"
    assert trace.error == "tool not found"


@pytest.mark.asyncio
async def test_response_includes_tool_traces():
    sm = TravelAgentStateMachine()
    resp = await sm.run("京都清水寺适合带父母去吗？", {"party": ["elderly"]})
    assert resp.tool_traces
    assert any(t.get("tool_name") for t in resp.tool_traces)
    assert any(t.get("status") for t in resp.tool_traces)


def test_no_direct_tool_run_in_place_research():
    source = inspect.getsource(PlaceResearchAgent)
    assert not re.search(r"self\.tools\.\w+\.run\(", source)
    assert "getattr(self.tools" not in source
    assert "run_tool" in source


@pytest.mark.asyncio
async def test_weather_tool_trace_when_weather_selected():
    sm = TravelAgentStateMachine()
    resp = await sm.run(
        "故宫明天天气怎么样，值得去吗？",
        {"travel_date": "2026-06-21", "party": ["family"]},
    )
    tool_names = {t["tool_name"] for t in resp.tool_traces}
    assert "weather" in tool_names
    weather_trace = next(t for t in resp.tool_traces if t["tool_name"] == "weather")
    assert weather_trace["status"] == "ok"
    assert weather_trace.get("evidence_ids")


@pytest.mark.asyncio
async def test_fallback_tool_trace_for_crowd_estimate():
    sm = TravelAgentStateMachine()
    resp = await sm.run("故宫今天人多吗？")
    tool_names = {t["tool_name"] for t in resp.tool_traces}
    assert "fallback" in tool_names
    combined = resp.answer + " ".join(resp.limitations)
    assert "实时" in combined or "估算" in combined
    assert resp.field_evidence_summary


@pytest.mark.asyncio
async def test_tool_traces_do_not_leak_between_requests():
    sm = TravelAgentStateMachine()
    first = await sm.run("京都清水寺适合带父母去吗？", {"party": ["elderly"]})
    first_count = len(first.tool_traces)
    assert first_count > 0

    second = await sm.run("这里人流量怎么样？")
    assert len(second.tool_traces) == 0


@pytest.mark.asyncio
async def test_weather_missing_location_records_error_trace():
    tools = ToolRegistry()
    agent = PlaceResearchAgent(tools)
    goal = UserGoal(place_candidates=["Some Place"])
    await agent.retrieve_for_place("Some Place", goal, ["weather"])
    trace = tools.traces[-1]
    assert trace.tool_name == "weather"
    assert trace.status == "error"
    assert trace.error == "missing destination_city or destination_country"


@pytest.mark.asyncio
async def test_lodging_missing_location_records_error_trace():
    tools = ToolRegistry()
    agent = PlaceResearchAgent(tools)
    goal = UserGoal(place_candidates=["Some Place"])
    await agent.retrieve_for_place("Some Place", goal, ["lodging"])
    trace = tools.traces[-1]
    assert trace.tool_name == "lodging"
    assert trace.status == "error"
    assert trace.error == "missing destination_city or destination_country"


@pytest.mark.asyncio
async def test_fallback_does_not_default_to_kyoto_when_location_missing():
    tools = ToolRegistry()
    agent = PlaceResearchAgent(tools)
    goal = UserGoal(place_candidates=["Unknown Spot"])
    await agent.retrieve_for_place("Unknown Spot", goal, ["fallback"])
    trace = tools.traces[-1]
    assert trace.tool_name == "fallback"
    assert trace.status == "error"
    assert trace.input.get("country") is None
    assert trace.input.get("city") is None
    assert trace.input.get("country") != "Japan"
    assert trace.input.get("city") != "Kyoto"


@pytest.mark.asyncio
async def test_fallback_trace_contains_actual_or_missing_location():
    tools = ToolRegistry()
    agent = PlaceResearchAgent(tools)

    goal_with_location = UserGoal(
        place_candidates=["Forbidden City"],
        destination_city="Beijing",
        destination_country="China",
    )
    await agent.retrieve_for_place("Forbidden City", goal_with_location, ["fallback"])
    ok_trace = tools.traces[-1]
    assert ok_trace.status == "ok"
    assert ok_trace.input.get("country") == "China"
    assert ok_trace.input.get("city") == "Beijing"

    tools.clear_traces()
    goal_missing = UserGoal(place_candidates=["Unknown Spot"])
    await agent.retrieve_for_place("Unknown Spot", goal_missing, ["fallback"])
    err_trace = tools.traces[-1]
    assert err_trace.status == "error"
    assert err_trace.input.get("country") is None
    assert err_trace.input.get("city") is None


@pytest.mark.asyncio
async def test_place_research_records_skipped_weather_trace():
    tools = ToolRegistry()
    agent = PlaceResearchAgent(tools)
    goal = UserGoal(place_candidates=["Some Place"])
    limitations: list[str] = []
    await agent.retrieve_for_place("Some Place", goal, ["weather"], limitations=limitations)
    assert limitations
    trace = tools.traces[-1]
    assert trace.tool_name == "weather"
    assert trace.status == "error"


@pytest.mark.asyncio
async def test_response_includes_field_evidence_and_citation_check():
    sm = TravelAgentStateMachine()
    resp = await sm.run("京都清水寺适合带父母去吗？", {"party": ["elderly"]})
    assert resp.field_evidence_summary
    assert any(row.get("field") for row in resp.field_evidence_summary)
    if resp.citation_check_result:
        assert "confidence" in resp.citation_check_result
        assert "limitations" in resp.citation_check_result
