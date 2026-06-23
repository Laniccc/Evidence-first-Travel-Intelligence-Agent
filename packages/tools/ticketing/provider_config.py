"""Ticket/review provider configuration helpers."""

from __future__ import annotations

from app.config import Settings, get_settings

TICKET_PROVIDER_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "ticketlens_experience_mcp",
        "ticketlens_experience_review_signal_mcp",
        "ctrip_review_crawler_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "dianping_review_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
        "ticket_snapshot_store",
        "ticket_price_history_query",
    }
)

TICKET_CRAWLER_TOOLS: frozenset[str] = frozenset(
    {
        "ctrip_review_crawler_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "dianping_review_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
    }
)

REVIEW_CRAWLER_TOOLS: frozenset[str] = frozenset(
    {
        "ctrip_review_crawler_mcp",
        "dianping_review_crawler_mcp",
        "ticketlens_experience_mcp",
        "ticketlens_experience_review_signal_mcp",
    }
)


def is_ticket_provider_tool(name: str) -> bool:
    return name in TICKET_PROVIDER_TOOL_NAMES


def ticketlens_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        s.ticketlens_enabled
        and s.ticketlens_api_key
        and s.ticketlens_api_base_url
    )


def ctrip_subprocess_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.ctrip_crawler_enabled and (s.ctrip_crawler_command or "").strip())


def ctrip_websearch_signal_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        s.ctrip_crawler_enabled
        and s.ctrip_websearch_signal_enabled
        and s.mcp_search_enabled
    )


def ctrip_crawler_configured(settings: Settings | None = None) -> bool:
    return ctrip_subprocess_configured(settings) or ctrip_websearch_signal_configured(settings)


def fliggy_top_api_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        s.fliggy_top_api_enabled
        and s.fliggy_ticket_crawler_enabled
        and s.enable_ticket_crawler_providers
        and s.fliggy_app_key
        and s.fliggy_app_secret
    )


def fliggy_api_configured(settings: Settings | None = None) -> bool:
    return fliggy_top_api_configured(settings)


def fliggy_crawler_configured(settings: Settings | None = None) -> bool:
    """Backward-compatible alias for Fliggy TOP API availability."""
    return fliggy_api_configured(settings)


def dianping_subprocess_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.dianping_crawler_enabled and (s.dianping_crawler_command or "").strip())


def dianping_websearch_signal_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        s.dianping_crawler_enabled
        and s.dianping_websearch_signal_enabled
        and s.mcp_search_enabled
    )


def dianping_crawler_configured(settings: Settings | None = None) -> bool:
    return dianping_subprocess_configured(settings) or dianping_websearch_signal_configured(settings)


def ticket_snapshot_store_enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.ticket_snapshot_store_enabled)


def provider_enabled_for_tool(tool_name: str, settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    if tool_name in {"ticketlens_experience_mcp", "ticketlens_experience_review_signal_mcp"}:
        return s.ticketlens_enabled
    if tool_name in {"ctrip_review_crawler_mcp", "ctrip_ticket_signal_crawler_mcp"}:
        return s.ctrip_crawler_enabled and (
            s.enable_review_crawler_providers or s.enable_ticket_crawler_providers
        )
    if tool_name == "fliggy_ticket_snapshot_crawler_mcp":
        return s.fliggy_ticket_crawler_enabled and s.enable_ticket_crawler_providers
    if tool_name in {"dianping_review_crawler_mcp", "dianping_ticket_signal_crawler_mcp"}:
        return s.dianping_crawler_enabled and (
            s.enable_review_crawler_providers or s.enable_ticket_crawler_providers
        )
    if tool_name in {"ticket_snapshot_store", "ticket_price_history_query"}:
        return s.ticket_snapshot_store_enabled
    return False


def provider_configured_for_tool(tool_name: str, settings: Settings | None = None) -> bool:
    if not provider_enabled_for_tool(tool_name, settings):
        return False
    s = settings or get_settings()
    if tool_name in {"ticketlens_experience_mcp", "ticketlens_experience_review_signal_mcp"}:
        return ticketlens_configured(s)
    if tool_name.startswith("ctrip_"):
        return ctrip_crawler_configured(s)
    if tool_name == "fliggy_ticket_snapshot_crawler_mcp":
        return fliggy_api_configured(s)
    if tool_name.startswith("dianping_"):
        return dianping_crawler_configured(s)
    if tool_name in {"ticket_snapshot_store", "ticket_price_history_query"}:
        return ticket_snapshot_store_enabled(s)
    return False
