from fastapi.testclient import TestClient

from app.api.app_factory import create_app
from app.api.health import ReadinessProbe
from app.config import Settings
from app.contracts.response import AgentQueryResponse


class Service:
    async def query(self, payload, *, trace_id=None):
        return AgentQueryResponse(answer="ok")


def app_client(*, qdrant: bool, requires_qdrant: bool = False):
    settings = Settings(
        _env_file=None,
        agent_service_key="secret",
        readiness_requires_qdrant=requires_qdrant,
    )
    app = create_app(
        settings_override=settings,
        agent_run_service=Service(),
        readiness_probe=ReadinessProbe(
            sqlite_probe=lambda: True, qdrant_probe=lambda: qdrant
        ),
    )
    return TestClient(app)


def test_live_is_process_only_and_ready_reports_qdrant_degradation():
    with app_client(qdrant=False) as client:
        live = client.get("/agent/health/live")
        ready = client.get("/agent/health/ready")

    assert live.json()["status"] == "ok"
    assert live.json()["checks"] == {"process": "ok"}
    assert ready.json()["status"] == "degraded"
    assert ready.json()["ready"] is True
    assert ready.json()["checks"]["qdrant"] == "unavailable"


def test_qdrant_can_be_configured_as_required_for_readiness():
    with app_client(qdrant=False, requires_qdrant=True) as client:
        ready = client.get("/agent/health/ready")

    assert ready.json()["status"] == "not_ready"
    assert ready.json()["ready"] is False


def test_configured_service_key_rejects_missing_or_wrong_key():
    with app_client(qdrant=True) as client:
        missing = client.post("/agent/query", json={"query": "故宫"})
        wrong = client.post(
            "/agent/query",
            headers={"X-Agent-Service-Key": "wrong"},
            json={"query": "故宫"},
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401
