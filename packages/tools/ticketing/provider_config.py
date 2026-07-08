"""Ticket/review provider configuration helpers."""

from __future__ import annotations

from app.config import Settings, get_settings

TICKET_PROVIDER_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "ticketlens_experience_mcp",
        "ticketlens_experience_review_signal_mcp",
        "ctrip_review_crawler_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "ctrip_guide_crawler_mcp",
        "fliggy_ticket_api_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "dianping_review_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
        "dianping_nearby_crawler_mcp",
        "ticket_snapshot_store",
        "ticket_price_history_query",
    }
)

TICKET_CRAWLER_TOOLS: frozenset[str] = frozenset(
    {
        "ctrip_review_crawler_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "fliggy_ticket_api_mcp",
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


CROWD_PROVIDER_TOOL_NAMES: frozenset[str] = frozenset({"crowd_estimation_mcp"})


def is_ticket_provider_tool(name: str) -> bool:
    return name in TICKET_PROVIDER_TOOL_NAMES


def is_crowd_provider_tool(name: str) -> bool:
    return name in CROWD_PROVIDER_TOOL_NAMES


def dianping_spider_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.dianping_crawler_enabled and (s.dianping_spider_command or "").strip())


def dianping_nearby_configured(settings: Settings | None = None) -> bool:
    return dianping_spider_configured(settings) or dianping_subprocess_configured(settings) or dianping_websearch_signal_configured(settings)


def crowd_estimation_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    if not s.enable_crowd_estimation_tools:
        return False
    if ctrip_subprocess_configured(s) or ctrip_websearch_signal_configured(s):
        return True
    if dianping_subprocess_configured(s) or dianping_websearch_signal_configured(s):
        return True
    if s.mcp_baidu_map_enabled and s.baidu_map_ak:
        return True
    return False


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


def fliggy_ticket_api_enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        s.fliggy_ticket_api_enabled
        or (s.fliggy_ticket_crawler_enabled and s.fliggy_top_api_enabled)
        or (s.fliggy_ticket_crawler_enabled and s.fliggy_flyai_enabled)
    )


def effective_flyai_api_key(settings: Settings | None = None) -> str | None:
    s = settings or get_settings()
    return (s.fliggy_flyai_api_key or "").strip() or None


def fliggy_flyai_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        s.fliggy_flyai_enabled
        and s.fliggy_ticket_crawler_enabled
        and s.enable_ticket_crawler_providers
        and effective_flyai_api_key(s)
    )


def fliggy_subprocess_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        s.fliggy_ticket_crawler_enabled
        and s.enable_ticket_crawler_providers
        and (s.fliggy_ticket_crawler_command or "").strip()
    )


def fliggy_ticket_api_key(settings: Settings | None = None) -> str | None:
    s = settings or get_settings()
    return (s.fliggy_ticket_api_key or s.fliggy_app_key or "").strip() or None


def fliggy_ticket_api_secret(settings: Settings | None = None) -> str | None:
    s = settings or get_settings()
    return (s.fliggy_ticket_api_secret or s.fliggy_app_secret or "").strip() or None


def fliggy_ticket_api_endpoint(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return (s.fliggy_ticket_api_endpoint or s.fliggy_api_gateway_url or "").strip()


def fliggy_top_api_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        (s.fliggy_ticket_api_enabled or (s.fliggy_ticket_crawler_enabled and s.fliggy_top_api_enabled))
        and s.enable_ticket_crawler_providers
        and fliggy_ticket_api_key(s)
        and fliggy_ticket_api_secret(s)
        and fliggy_ticket_api_endpoint(s)
    )


def fliggy_crawler_configured(settings: Settings | None = None) -> bool:
    """Any working Fliggy path: FlyAI, TOP API, or subprocess CLI."""
    return (
        fliggy_flyai_configured(settings)
        or fliggy_top_api_configured(settings)
        or fliggy_subprocess_configured(settings)
    )


def fliggy_api_block_reason(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    if not s.fliggy_ticket_crawler_enabled:
        return "disabled_by_config"
    if not s.enable_ticket_crawler_providers:
        return "disabled_by_config"
    if fliggy_flyai_configured(s) or fliggy_top_api_configured(s) or fliggy_subprocess_configured(s):
        return ""
    if s.fliggy_flyai_enabled and not effective_flyai_api_key(s):
        return "missing_config"
    if (s.fliggy_ticket_api_enabled or s.fliggy_top_api_enabled) and (
        not fliggy_ticket_api_key(s) or not fliggy_ticket_api_secret(s)
    ):
        return "missing_config"
    if s.fliggy_flyai_enabled:
        return "missing_config"
    return "disabled_by_config"


def fliggy_api_configured(settings: Settings | None = None) -> bool:
    return fliggy_crawler_configured(settings)


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
    if tool_name == "ctrip_guide_crawler_mcp":
        return s.ctrip_crawler_enabled and s.enable_travel_note_crawlers
    if tool_name in {"fliggy_ticket_api_mcp", "fliggy_ticket_snapshot_crawler_mcp"}:
        return fliggy_ticket_api_enabled(s) and s.enable_ticket_crawler_providers
    if tool_name in {"dianping_review_crawler_mcp", "dianping_ticket_signal_crawler_mcp"}:
        return s.dianping_crawler_enabled and (
            s.enable_review_crawler_providers or s.enable_ticket_crawler_providers
        )
    if tool_name == "dianping_nearby_crawler_mcp":
        return s.dianping_crawler_enabled and s.enable_nearby_platform_crawlers
    if tool_name == "crowd_estimation_mcp":
        return s.enable_crowd_estimation_tools
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
    if tool_name == "ctrip_guide_crawler_mcp":
        return ctrip_crawler_configured(s)
    if tool_name in {"fliggy_ticket_api_mcp", "fliggy_ticket_snapshot_crawler_mcp"}:
        return fliggy_crawler_configured(s)
    if tool_name == "dianping_nearby_crawler_mcp":
        return dianping_nearby_configured(s)
    if tool_name.startswith("dianping_"):
        return dianping_crawler_configured(s)
    if tool_name == "crowd_estimation_mcp":
        return crowd_estimation_configured(s)
    if tool_name in {"ticket_snapshot_store", "ticket_price_history_query"}:
        return ticket_snapshot_store_enabled(s)
    return False
