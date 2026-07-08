from contextlib import asynccontextmanager

# Ensure uvicorn --reload picks up shared packages/tools changes (subprocess argv, crawlers).
import tools.crawlers.fliggy_crawler_tool  # noqa: F401
import tools.subprocess_argv  # noqa: F401

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.contract import AgentQueryRequest, AgentQueryResponse
from app.debug_session_log import write_debug_session_md
from app.logging_config import get_logger, setup_logging
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.tool_gateway.integration import install_java_tool_gateway

_settings = None
_state_machine = None
_logger = get_logger("travel_agent")


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    global _settings, _state_machine
    _settings = get_settings()
    setup_logging(_settings.log_level)
    if not _settings.llm_api_key():
        raise RuntimeError(
            "DEEPSEEK_API_KEY or ANTHROPIC_API_KEY is required. "
            "Configure apps/agent-python/.env before starting the agent."
        )
    install_java_tool_gateway()
    _state_machine = TravelAgentStateMachine()
    fastapi_app.version = _settings.app_version
    fastapi_app.title = _settings.app_name
    yield


app = FastAPI(title="Travel Agent Python", version="0.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/agent/health")
async def agent_health():
    version = _settings.app_version if _settings else "unknown"
    llm_configured = bool(_settings and _settings.llm_api_key())
    return {
        "status": "ok" if llm_configured else "degraded",
        "service": "agent-python",
        "version": version,
        "llm_mode": "anthropic",
        "llm_configured": llm_configured,
    }


@app.post("/agent/query", response_model=AgentQueryResponse)
async def agent_query(payload: AgentQueryRequest):
    if not _settings or not _settings.llm_api_key():
        raise HTTPException(
            status_code=503,
            detail="LLM API key not configured; set DEEPSEEK_API_KEY in .env",
        )
    user_context = dict(payload.user_context or {})
    if payload.session_id and "session_id" not in user_context:
        user_context["session_id"] = payload.session_id

    result = await _state_machine.run(payload.query, user_context)
    try:
        write_debug_session_md(payload.query, result)
    except Exception as exc:
        _logger.warning("debug_session_log_failed", error=str(exc))
    return AgentQueryResponse.from_legacy(result, session_id=payload.session_id)
