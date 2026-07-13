"""Health response assembly for the Agent HTTP API."""

from app.contracts.response import AgentHealthResponse


def build_health_response(settings) -> AgentHealthResponse:
    version = settings.app_version if settings else "unknown"
    llm_configured = bool(settings and settings.llm_api_key())
    return AgentHealthResponse(
        status="ok" if llm_configured else "degraded",
        service="agent-python",
        version=version,
        llm_mode="anthropic",
        llm_configured=llm_configured,
    )
