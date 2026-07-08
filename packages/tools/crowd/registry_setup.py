"""Register crowd estimation provider on TravelToolRegistry."""

from __future__ import annotations

import logging

from app.config import get_settings
from tools.crowd.crowd_estimation_tool import CrowdEstimationTool
from tools.ticketing.provider_config import crowd_estimation_configured

logger = logging.getLogger(__name__)


def attach_crowd_providers(registry) -> list[str]:
    settings = getattr(registry, "settings", None) or get_settings()
    registered: list[str] = []
    if not crowd_estimation_configured(settings):
        logger.debug("Skipping crowd_estimation_mcp (disabled or not configured)")
        return registered
    if getattr(registry, "crowd_estimation_mcp", None) is not None:
        return registered
    tool = CrowdEstimationTool(settings, registry=registry)
    registry.crowd_estimation_mcp = tool
    registered.append("crowd_estimation_mcp")
    logger.info("Registered crowd provider crowd_estimation_mcp")
    return registered
