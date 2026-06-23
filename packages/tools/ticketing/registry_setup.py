"""Register ticket/review provider tools on TravelToolRegistry."""

from __future__ import annotations

import logging

from app.config import get_settings
from tools.crawlers.ctrip_crawler_tool import build_ctrip_tools
from tools.crawlers.dianping_crawler_tool import build_dianping_tools
from tools.crawlers.fliggy_crawler_tool import build_fliggy_tools
from tools.ticketing.provider_config import provider_configured_for_tool
from tools.ticketing.ticket_snapshot_store import TicketSnapshotStore
from tools.ticketing.ticketlens_tool import (
    TicketLensExperienceTool,
    TicketLensReviewSignalTool,
    TicketPriceHistoryQueryTool,
    TicketSnapshotStoreTool,
)

logger = logging.getLogger(__name__)


def attach_ticket_providers(registry) -> list[str]:
    settings = getattr(registry, "settings", None) or get_settings()
    registered: list[str] = []
    snapshot_store = None
    if settings.ticket_snapshot_store_enabled:
        snapshot_store = TicketSnapshotStore(settings.ticket_snapshot_db_path)

    candidates: dict[str, object] = {
        "ticketlens_experience_mcp": TicketLensExperienceTool(settings, snapshot_store),
        "ticketlens_experience_review_signal_mcp": TicketLensReviewSignalTool(settings, snapshot_store),
        "ticket_snapshot_store": TicketSnapshotStoreTool(settings, snapshot_store),
        "ticket_price_history_query": TicketPriceHistoryQueryTool(settings, snapshot_store),
    }
    candidates.update(build_ctrip_tools(settings))
    candidates.update(build_fliggy_tools(settings, snapshot_store))
    candidates.update(build_dianping_tools(settings))

    for policy_name, tool in candidates.items():
        if not provider_configured_for_tool(policy_name, settings):
            logger.debug("Skipping ticket provider %s (disabled or not configured)", policy_name)
            continue
        attr = policy_name
        if getattr(registry, attr, None) is not None:
            continue
        setattr(registry, attr, tool)
        registered.append(policy_name)
        logger.info("Registered ticket provider %s", policy_name)
    return registered
