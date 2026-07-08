import json
from pathlib import Path

import pytest

from app.orchestrator.state_machine import TravelAgentStateMachine


QUERIES_PATH = Path(__file__).resolve().parent / "real_data_pilot_queries.json"


@pytest.mark.asyncio
@pytest.mark.parametrize("query", json.loads(QUERIES_PATH.read_text(encoding="utf-8")))
async def test_real_data_pilot_queries_mock_mode(query: str):
    orchestrator = TravelAgentStateMachine()
    response = await orchestrator.run(query)
    assert response.answer
    assert response.visible_trace is not None
    assert response.field_evidence_summary is not None
    assert isinstance(response.limitations, list)
