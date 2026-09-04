from fastapi.testclient import TestClient

from app.api.app_factory import create_app
from app.api.health import ReadinessProbe
from app.config import Settings
from app.contracts.response import AgentQueryResponse
from app.orchestration.agent_run_service import AgentRunService
import pytest


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


def test_publication_fields_are_optional_for_old_responses():
    response = AgentQueryResponse(answer="legacy")
    assert response.promotion_summary is None
    assert response.index_sync_status is None


@pytest.mark.parametrize("status,index_status", [("rejected", "not_applicable"),
    ("pending_review", "not_applicable"), ("published", "pending"), ("published", "indexed")])
def test_api_keeps_typed_publication_snapshot(status, index_status):
    class ObservedService:
        async def query(self, payload, **kwargs):
            return AgentQueryResponse(answer="safe answer", promotion_summary={"status": status},
                index_sync_status={"status": index_status},
                orchestration_summary={"terminal_state": "safe_failure", "run_id": "r"})
    app = create_app(settings_override=Settings(_env_file=None, agent_service_key=None),
        agent_run_service=ObservedService(), readiness_probe=ReadinessProbe(sqlite_probe=lambda: True, qdrant_probe=lambda: True))
    with TestClient(app) as client:
        result = client.post("/agent/query", json={"query": "颐和园地址"})
    assert result.status_code == 200
    assert result.json()["promotion_summary"]["status"] == status
    assert result.json()["index_sync_status"]["status"] == index_status


def test_json_schema_and_publication_models_share_strict_additive_contract():
    import json
    from pathlib import Path
    import jsonschema
    from pydantic import ValidationError
    from app.contracts.response import PromotionSummary, IndexSyncStatus
    schema = json.loads((Path(__file__).parents[4] / "contracts/schemas/travel_query_response.schema.json").read_text())
    for name, model, status in (("promotion_summary", PromotionSummary, "published"),
                                ("index_sync_status", IndexSyncStatus, "pending")):
        assert name not in schema["required"]
        jsonschema.validate(model(status=status).model_dump(), schema["properties"][name])
        jsonschema.validate(None, schema["properties"][name])
        with pytest.raises(ValidationError):
            model(status=status, raw_payload="private-key")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"status": status, "raw_payload": "private"}, schema["properties"][name])
