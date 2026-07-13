"""Agent HTTP routes."""

from fastapi import APIRouter, HTTPException, Request

from app.api.health import build_health_response
from app.contracts.request import AgentQueryRequest
from app.contracts.response import AgentHealthResponse, AgentQueryResponse

router = APIRouter(prefix="/agent")


@router.get("/health", response_model=AgentHealthResponse)
async def agent_health(request: Request) -> AgentHealthResponse:
    settings = getattr(request.app.state, "settings", None)
    return build_health_response(settings)


@router.post("/query", response_model=AgentQueryResponse)
async def agent_query(payload: AgentQueryRequest, request: Request) -> AgentQueryResponse:
    settings = getattr(request.app.state, "settings", None)
    if not settings or not settings.llm_api_key():
        raise HTTPException(
            status_code=503,
            detail="LLM API key not configured; set DEEPSEEK_API_KEY in .env",
        )

    service = getattr(request.app.state, "agent_run_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Agent run service is not initialized")

    return await service.query(payload)
