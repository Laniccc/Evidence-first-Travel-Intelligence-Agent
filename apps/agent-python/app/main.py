"""Deep Research Agent Platform — FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.debug.routes import debug_router
from app.agent_core.runtime import AgentCoreRuntime
from app.llm_client import LLMClient
from app.logging_config import get_logger, setup_logging
from app.schemas.study import StudyQueryRequest, StudyQueryResponse
from app.tools.mcp_search import SearchTool, ToolRegistry

_settings = None
_agent_runtime = None
_logger = get_logger("deep_research_agent")


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    global _settings, _agent_runtime
    _settings = get_settings()
    setup_logging(_settings.log_level)

    # Initialize LLM client
    llm_client = None
    try:
        llm_client = LLMClient()
        _logger.info("LLM client initialized: %s", _settings.llm_model())
    except Exception as e:
        _logger.warning("LLM client not available: %s", e)

    # Initialize tool registry (MCP search)
    tools = None
    try:
        search = SearchTool(server_url=_settings.mcp_search_server_url)
        tools = ToolRegistry(search)
        _logger.info("Tool registry initialized (search: %s)", _settings.mcp_search_server_url)
    except Exception as e:
        _logger.warning("Tool registry not available: %s", e)

    _agent_runtime = AgentCoreRuntime(
        tools_registry=tools,
        llm_client=llm_client,
    )
    fastapi_app.title = _settings.app_name
    fastapi_app.version = _settings.app_version
    yield


app = FastAPI(title="Deep Research Agent", version="0.1.0", lifespan=lifespan)
app.include_router(debug_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/agent/health")
async def health():
    version = _settings.app_version if _settings else "unknown"
    llm_configured = bool(_settings and _settings.llm_api_key())
    return {
        "status": "ok" if llm_configured else "degraded",
        "service": "deep-research-agent",
        "version": version,
        "llm_configured": llm_configured,
    }


@app.post("/agent/query")
async def agent_query(payload: StudyQueryRequest):
    if _agent_runtime is None:
        raise HTTPException(status_code=503, detail="Agent runtime not initialized")

    result = await _agent_runtime.run(
        query=payload.query,
        user_context=payload.user_context,
        session_id=payload.session_id,
    )

    return {
        "status": result.get("status", "error"),
        "run_id": result.get("run_id"),
        "report": result.get("report"),
        "message": result.get("message"),
        "evidence_count": result.get("evidence_count", 0),
        "quality_evidence_count": result.get("quality_evidence_count", 0),
        "phases_completed": result.get("phases_completed", []),
        "rounds": result.get("rounds", []),
        "gate_results": result.get("gate_results", {}),
        "errors": result.get("errors", []),
        "session_id": payload.session_id,
    }


@app.get("/agent/runs/{run_id}/projection")
async def run_projection(run_id: str):
    if _agent_runtime is None:
        raise HTTPException(status_code=503, detail="Agent runtime not initialized")
    store = _agent_runtime.get_store(run_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return store.project_run().model_dump(mode="json")
