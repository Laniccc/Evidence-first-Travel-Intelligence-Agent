"""FastAPI application factory and concrete runtime dependency composition."""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import ReadinessProbe
from app.api.routes import router as agent_router
from app.config import get_settings
from app.observability.debug_session import write_agent_debug_session
from app.observability.logging import get_logger, setup_logging
from app.orchestration.agent_run_service import create_agent_run_service

_logger = get_logger("travel_agent")


def create_app(
    *,
    settings_override=None,
    agent_run_service=None,
    readiness_probe: ReadinessProbe | None = None,
    runtime_builder=None,
) -> FastAPI:
    resources: dict = {}

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        settings = settings_override or get_settings()
        setup_logging(settings.log_level)
        fastapi_app.state.settings = settings

        service = agent_run_service
        probe = readiness_probe
        if service is None:
            if runtime_builder is None:
                service = create_agent_run_service(
                    debug_writer=write_agent_debug_session,
                    logger=_logger,
                    debug_enabled=settings.debug,
                )
            else:
                service, probe, resources["runtime_resource"] = runtime_builder(settings)
        fastapi_app.state.agent_run_service = service
        fastapi_app.state.readiness_probe = probe
        fastapi_app.version = settings.app_version
        fastapi_app.title = settings.app_name
        yield
        resource = resources.get("runtime_resource")
        if resource is not None and hasattr(resource, "close"):
            resource.close()

    fastapi_app = FastAPI(
        title="Travel Agent Python", version="0.0.0", lifespan=lifespan
    )
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    fastapi_app.include_router(agent_router)
    return fastapi_app
__all__ = ["create_app"]
