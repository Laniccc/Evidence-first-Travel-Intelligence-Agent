from fastapi.testclient import TestClient

from app.api.app_factory import create_app
from app.api.health import ReadinessProbe
from app.config import Settings
from app.contracts.response import AgentQueryResponse
from app.orchestration.agent_run_service import AgentRunService


class RecordingService:
    def __init__(self):
        self.calls = []

    async def query(self, payload, *, trace_id=None):
        self.calls.append((payload, trace_id))
        return AgentQueryResponse(
            answer="有证据的答案",
            session_id=payload.session_id,
            query_id="query-1",
            orchestration_summary={"trace_id": trace_id},
        )


def test_query_propagates_trace_session_debug_and_service_key():
    settings = Settings(_env_file=None, agent_service_key="service-secret")
    service = RecordingService()
    app = create_app(
        settings_override=settings,
        agent_run_service=service,
        readiness_probe=ReadinessProbe(
            sqlite_probe=lambda: True, qdrant_probe=lambda: True
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/agent/query",
            headers={
                "X-Agent-Service-Key": "service-secret",
                "X-Trace-Id": "trace-1",
            },
            json={"query": "故宫几点开放", "session_id": "session-1", "debug": True},
        )

    assert response.status_code == 200
    assert service.calls[0][0].session_id == "session-1"
    assert service.calls[0][0].debug is True
    assert service.calls[0][1] == "trace-1"
    assert response.json()["orchestration_summary"]["trace_id"] == "trace-1"


class TypedMachine:
    async def run(self, query, user_context, session_id, *, debug=False, trace_id=None):
        return AgentQueryResponse(
            answer="ok", session_id=session_id, query_id="q-1"
        )


class Logger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


async def test_debug_file_requires_payload_and_server_switch():
    writes = []
    service = AgentRunService(
        TypedMachine(),
        lambda query, result: writes.append((query, result)),
        Logger(),
        debug_enabled=False,
    )

    from app.contracts.request import AgentQueryRequest

    await service.query(AgentQueryRequest(query="故宫", debug=True))
    assert writes == []
