import json
from pathlib import Path

import pytest

from app.agents.intent_agent import IntentAgent, RegionGateAgent
from app.orchestrator.state_machine import TravelAgentStateMachine


GOLDEN_PATH = Path(__file__).parent / "golden_queries.json"


@pytest.fixture
def golden_queries():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_region_gate_accuracy(golden_queries):
    for item in golden_queries:
        result = RegionGateAgent.run(item["query"])
        assert result.supported
        assert result.country == item["country"]


@pytest.mark.asyncio
async def test_intent_classification(golden_queries):
    for item in golden_queries:
        goal = IntentAgent.parse_deterministic(item["query"])
        assert goal.intent_type.value == item["expected_intent"]


@pytest.mark.asyncio
async def test_end_to_end_structure(golden_queries):
    sm = TravelAgentStateMachine()
    for item in golden_queries:
        resp = await sm.run(item["query"])
        assert resp.answer
        assert resp.visible_trace
        assert resp.confidence > 0
        joined = resp.answer + " ".join(resp.visible_trace)
        for token in item["must_include"]:
            assert token in joined or token in json.dumps(resp.model_dump(), ensure_ascii=False)


@pytest.mark.asyncio
async def test_kiyomizu_elderly_sample():
    sm = TravelAgentStateMachine()
    resp = await sm.run("京都清水寺适合带父母去吗？", {"party": ["elderly"], "pace": "relaxed"})
    assert "清水寺" in resp.answer or "Kiyomizu" in resp.answer
    assert resp.evidence_summary
    assert any("Official" in e["source_name"] or "Mock" in e["source_name"] for e in resp.evidence_summary)
