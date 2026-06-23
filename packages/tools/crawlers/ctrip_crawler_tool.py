"""Ctrip crawler wrappers."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from tools.crawlers.base_crawler_tool import BaseCrawlerTool
from tools.crawlers.platform_signal_crawler_mixin import PlatformSignalCrawlerMixin
from tools.ticketing.evidence_normalizer import normalize_review_crawler_payload


class CtripReviewCrawlerTool(PlatformSignalCrawlerMixin, BaseCrawlerTool):
    provider_name = "Ctrip"
    policy_name = "ctrip_review_crawler_mcp"
    platform = "ctrip"
    websearch_flag_attr = "ctrip_websearch_signal_enabled"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        s = self.settings
        self.enabled = s.ctrip_crawler_enabled and s.enable_review_crawler_providers
        self.command = s.ctrip_crawler_command or ""
        self.workdir = s.ctrip_crawler_workdir or None
        self.timeout_seconds = s.ctrip_crawler_timeout_seconds
        self.max_results = s.ctrip_crawler_max_results
        self._init_platform_signal()

    def _normalize(self, data: dict[str, Any] | list, *, place_name: str, city: str | None, country: str) -> list:
        payload = data if isinstance(data, dict) else {"items": data}
        return normalize_review_crawler_payload(
            "Ctrip", payload, place_name=place_name, city=city, country=country
        )


class CtripTicketSignalCrawlerTool(PlatformSignalCrawlerMixin, BaseCrawlerTool):
    provider_name = "Ctrip"
    policy_name = "ctrip_ticket_signal_crawler_mcp"
    platform = "ctrip"
    websearch_flag_attr = "ctrip_websearch_signal_enabled"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        s = self.settings
        self.enabled = s.ctrip_crawler_enabled and s.enable_ticket_crawler_providers
        self.command = s.ctrip_crawler_command or ""
        self.workdir = s.ctrip_crawler_workdir or None
        self.timeout_seconds = s.ctrip_crawler_timeout_seconds
        self.max_results = s.ctrip_crawler_max_results
        self._init_platform_signal()

    def _normalize(self, data: dict[str, Any] | list, *, place_name: str, city: str | None, country: str) -> list:
        payload = data if isinstance(data, dict) else {"items": data}
        return normalize_review_crawler_payload(
            "Ctrip", payload, place_name=place_name, city=city, country=country
        )


def build_ctrip_tools(settings: Settings | None = None) -> dict[str, BaseCrawlerTool]:
    s = settings or get_settings()
    return {
        "ctrip_review_crawler_mcp": CtripReviewCrawlerTool(s),
        "ctrip_ticket_signal_crawler_mcp": CtripTicketSignalCrawlerTool(s),
    }
