from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.logging_config import bind_request_context, get_logger, setup_logging
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.response import TravelQueryRequest, TravelQueryResponse

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger("travel_agent")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

state_machine = TravelAgentStateMachine()


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    ctx = bind_request_context()
    request.state.context = ctx
    response = await call_next(request)
    response.headers["X-Request-Id"] = ctx["request_id"]
    return response


@app.get("/")
async def root():
    index = STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return RedirectResponse(url="/docs")


@app.get("/admin")
async def admin():
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.app_version}


@app.get("/api/travel/supported-regions")
async def supported_regions():
    return {"countries": settings.supported_countries, "cities": settings.supported_cities}


@app.post("/api/travel/query", response_model=TravelQueryResponse)
async def travel_query(payload: TravelQueryRequest):
    logger.info("travel_query_received", query=payload.query[:200], debug=payload.debug)
    result = await state_machine.run(payload.query, payload.user_context)
    logger.info(
        "travel_query_completed",
        query_id=result.query_id,
        confidence=result.confidence,
        trace_steps=len(result.visible_trace),
        evidence_count=len(result.evidence_summary),
    )
    return result
