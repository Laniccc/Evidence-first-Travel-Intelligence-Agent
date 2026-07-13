import pytest

from app.contracts.request import AgentQueryRequest
from app.contracts.response import AgentQueryResponse
from app.orchestration.agent_run_service import AgentRunService


class StructuredResult:
    def model_dump(self):
        return {"trip_type": "evidence-first"}


class LegacyResult:
    answer = "Use evidence-backed planning."
    session_id = None
    query_id = "query-1"
    visible_trace = ["understood", "planned"]
    evidence_summary = [{"source_url": "https://example.test/source"}]
    limitations = ["sample limitation"]
    confidence = 0.82
    tool_traces = [{"tool": "sample"}]
    structured_result = StructuredResult()
    field_evidence_summary = [{"field": "answer"}]
    conflicts = [{"field": "price"}]
    citation_check_result = {"passed": True}
    semantic_frame_summary = {"intent": "travel"}
    answer_mode = "summary"


class FakeStateMachine:
    def __init__(self):
        self.calls = []

    async def run(self, query: str, user_context: dict):
        self.calls.append((query, user_context))
        return LegacyResult()


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, event: str, **kwargs):
        self.warnings.append((event, kwargs))


def test_contract_models_are_owned_by_final_contract_modules():
    assert AgentQueryRequest.__module__ == "app.contracts.request"
    assert AgentQueryResponse.__module__ == "app.contracts.response"


def test_response_from_legacy_keeps_java_consumed_fields_stable():
    response = AgentQueryResponse.from_legacy(LegacyResult(), session_id="session-1")

    assert response.answer == "Use evidence-backed planning."
    assert response.session_id == "session-1"
    assert response.query_id == "query-1"
    assert response.visible_trace == ["understood", "planned"]
    assert response.evidence_summary == [{"source_url": "https://example.test/source"}]
    assert response.limitations == ["sample limitation"]
    assert response.confidence == 0.82
    assert response.tool_traces == [{"tool": "sample"}]
    assert response.structured_result == {"trip_type": "evidence-first"}
    assert response.field_evidence_summary == [{"field": "answer"}]
    assert response.conflicts == [{"field": "price"}]
    assert response.citation_check_result == {"passed": True}
    assert response.semantic_frame_summary == {"intent": "travel"}
    assert response.answer_mode == "summary"


@pytest.mark.asyncio
async def test_agent_run_service_delegates_to_state_machine_and_writes_debug_log():
    state_machine = FakeStateMachine()
    debug_calls = []
    service = AgentRunService(
        state_machine=state_machine,
        debug_writer=lambda query, result: debug_calls.append((query, result)),
        logger=FakeLogger(),
    )

    payload = AgentQueryRequest(
        query="Plan a Java internship trip",
        session_id="session-2",
        user_context={"user_id": "user-1"},
    )
    response = await service.query(payload)

    assert state_machine.calls == [
        (
            "Plan a Java internship trip",
            {"user_id": "user-1", "session_id": "session-2"},
        )
    ]
    assert len(debug_calls) == 1
    assert debug_calls[0][0] == "Plan a Java internship trip"
    assert isinstance(debug_calls[0][1], LegacyResult)
    assert response.session_id == "session-2"
