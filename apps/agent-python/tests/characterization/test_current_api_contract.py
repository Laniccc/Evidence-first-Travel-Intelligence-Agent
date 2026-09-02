from unittest.mock import Mock

import pytest

from app.contracts.request import AgentQueryRequest
from app.orchestration.agent_run_service import AgentRunService


class LegacyResult:
    answer = "Use evidence-backed planning."
    session_id = None
    query_id = "query-1"
    visible_trace = []
    evidence_summary = [{"source_url": "https://example.test/source"}]
    limitations = []
    confidence = 0.82
    tool_traces = []
    structured_result = None
    field_evidence_summary = []
    conflicts = []
    citation_check_result = {"passed": True}
    semantic_frame_summary = {"intent": "travel"}
    answer_mode = "summary"


class RecordingStateMachine:
    def __init__(self):
        self.calls: list[dict] = []

    async def run(
        self,
        query: str,
        user_context: dict,
        session_id: str | None = None,
        *,
        debug: bool = False,
        trace_id: str | None = None,
    ):
        self.calls.append(
            {
                "query": query,
                "user_context": user_context,
                "session_id": session_id,
                "debug": debug,
                "trace_id": trace_id,
            }
        )
        return LegacyResult()


@pytest.mark.asyncio
async def test_query_propagates_session_and_keeps_public_contract():
    machine = RecordingStateMachine()
    writer = Mock()
    service = AgentRunService(machine, writer, logger=Mock())

    response = await service.query(
        AgentQueryRequest(query="故宫需要预约吗", session_id="s-1", debug=False)
    )

    assert machine.calls[0]["session_id"] == "s-1"
    assert machine.calls[0]["debug"] is False
    assert response.model_dump().keys() >= {
        "answer",
        "session_id",
        "query_id",
        "evidence_summary",
        "limitations",
        "confidence",
        "citation_check_result",
    }
    writer.assert_not_called()


@pytest.mark.asyncio
async def test_debug_writer_is_opt_in():
    machine = RecordingStateMachine()
    writer = Mock()
    service = AgentRunService(machine, writer, logger=Mock())

    await service.query(AgentQueryRequest(query="比较故宫和颐和园", debug=True))

    writer.assert_called_once()
