"""Register official source discovery tools on TravelToolRegistry."""

from __future__ import annotations

import logging

from app.config import get_settings
from tools.official_source.official_source_discovery_tool import OfficialSourceDiscoveryTool

logger = logging.getLogger(__name__)

OFFICIAL_SOURCE_TOOL_NAMES: frozenset[str] = frozenset({"official_source_discovery_mcp"})


def is_official_source_tool(name: str) -> bool:
    return name in OFFICIAL_SOURCE_TOOL_NAMES


def attach_official_source_tools(registry) -> list[str]:
    settings = getattr(registry, "settings", None) or get_settings()
    if not getattr(settings, "official_source_discovery_enabled", True):
        return []

    registered: list[str] = []
    tool = OfficialSourceDiscoveryTool()
    if getattr(registry, "official_source_discovery_mcp", None) is None:
        registry.official_source_discovery_mcp = tool
        registered.append("official_source_discovery_mcp")
        logger.info("Registered official source tool official_source_discovery_mcp")
    return registered
