"""Agent HTTP routes."""

import secrets

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.health import build_health_response, build_live_response, build_ready_response
from app.contracts.request import AgentQueryRequest
from app.contracts.response import AgentHealthResponse, AgentQueryResponse

router = APIRouter(prefix="/agent")


@router.get("/health", response_model=AgentHealthResponse)
async def agent_health(request: Request) -> AgentHealthResponse:
    settings = getattr(request.app.state, "settings", None)
    return build_health_response(settings)


@router.get("/health/live", response_model=AgentHealthResponse)
async def agent_live(request: Request) -> AgentHealthResponse:
    return build_live_response(getattr(request.app.state, "settings", None))


@router.get("/health/ready", response_model=AgentHealthResponse)
async def agent_ready(request: Request) -> AgentHealthResponse:
    return build_ready_response(
        getattr(request.app.state, "settings", None),
        getattr(request.app.state, "readiness_probe", None),
    )


@router.post("/query", response_model=AgentQueryResponse)
async def agent_query(
    payload: AgentQueryRequest,
    request: Request,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
    x_agent_service_key: str | None = Header(
        default=None, alias="X-Agent-Service-Key"
    ),
) -> AgentQueryResponse:
    settings = getattr(request.app.state, "settings", None)
    expected_key = settings.agent_service_key if settings else None
    if expected_key and not secrets.compare_digest(
        x_agent_service_key or "", expected_key
    ):
        raise HTTPException(status_code=401, detail="invalid Agent service key")

    service = getattr(request.app.state, "agent_run_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Agent run service is not initialized")

    return await service.query(payload, trace_id=x_trace_id)
