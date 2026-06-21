from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app._legacy import get_settings, get_state_machine
from app.contract import AgentQueryRequest, AgentQueryResponse
from app.orchestrator.model_prior_routing import apply_model_prior_s5_routing
from app.tool_gateway.integration import install_java_tool_gateway

_settings = None
_state_machine = None


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    global _settings, _state_machine
    _settings = get_settings()
    install_java_tool_gateway()
    _state_machine = get_state_machine()
    apply_model_prior_s5_routing()
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
    return AgentQueryResponse.from_legacy(result, session_id=payload.session_id)
