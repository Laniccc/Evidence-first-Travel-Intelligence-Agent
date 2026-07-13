"""FastAPI application factory for the Agent service."""

from contextlib import asynccontextmanager
import importlib

# Ensure uvicorn --reload picks up shared packages/tools changes (subprocess argv, crawlers).
import tools.crawlers.fliggy_crawler_tool  # noqa: F401
import tools.subprocess_argv  # noqa: F401

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as agent_router
from app.config import get_settings
from app.observability.debug_session import write_agent_debug_session
from app.observability.logging import get_logger, setup_logging
from app.orchestration.agent_run_service import create_agent_run_service

_logger = get_logger("travel_agent")


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    fastapi_app.state.settings = settings

    if not settings.llm_api_key():
        raise RuntimeError(
            "DEEPSEEK_API_KEY or ANTHROPIC_API_KEY is required. "
            "Configure apps/agent-python/.env before starting the agent."
        )

    importlib.import_module(
        "app.integrations.java_gateway.integration"
    ).install_java_tool_gateway()
    fastapi_app.state.agent_run_service = create_agent_run_service(
        debug_writer=write_agent_debug_session,
        logger=_logger,
    )
    fastapi_app.version = settings.app_version
    fastapi_app.title = settings.app_name
    yield


def create_app() -> FastAPI:
    fastapi_app = FastAPI(title="Travel Agent Python", version="0.0.0", lifespan=lifespan)
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    fastapi_app.include_router(agent_router)
    return fastapi_app
