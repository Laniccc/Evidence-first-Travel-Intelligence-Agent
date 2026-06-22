from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.contract import AgentQueryRequest, AgentQueryResponse
from app.debug_session_log import write_debug_session_md
from app.logging_config import setup_logging
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.tool_gateway.integration import install_java_tool_gateway

_settings = None
_state_machine = None


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    global _settings, _state_machine
    _settings = get_settings()
    setup_logging(_settings.log_level)
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
    return {"status": "ok", "service": "agent-python", "version": version}


@app.post("/agent/query", response_model=AgentQueryResponse)
async def agent_query(payload: AgentQueryRequest):
    user_context = dict(payload.user_context or {})
    if payload.session_id and "session_id" not in user_context:
        user_context["session_id"] = payload.session_id

    result = await _state_machine.run(payload.query, user_context)
    try:
        write_debug_session_md(payload.query, result)
    except Exception:
        pass
    return AgentQueryResponse.from_legacy(result, session_id=payload.session_id)
