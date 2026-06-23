"""Dianping crawler wrappers."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from tools.crawlers.base_crawler_tool import BaseCrawlerTool
from tools.ticketing.evidence_normalizer import normalize_dianping_payload


class DianpingReviewCrawlerTool(BaseCrawlerTool):
    provider_name = "Dianping"
    policy_name = "dianping_review_crawler_mcp"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        s = self.settings
        self.enabled = s.dianping_crawler_enabled and s.enable_review_crawler_providers
        self.command = s.dianping_crawler_command or ""
        self.workdir = s.dianping_crawler_workdir or None
        self.timeout_seconds = s.dianping_crawler_timeout_seconds
        self.max_results = s.dianping_crawler_max_results

    def _normalize(self, data: dict[str, Any] | list, *, place_name: str, city: str | None, country: str) -> list:
        payload = data if isinstance(data, dict) else {"items": data}
        return normalize_dianping_payload(
            payload, place_name=place_name, city=city, country=country, ticket_signal=False
        )


class DianpingTicketSignalCrawlerTool(BaseCrawlerTool):
    provider_name = "Dianping"
    policy_name = "dianping_ticket_signal_crawler_mcp"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        s = self.settings
        self.enabled = s.dianping_crawler_enabled and s.enable_review_crawler_providers
        self.command = s.dianping_crawler_command or ""
        self.workdir = s.dianping_crawler_workdir or None
        self.timeout_seconds = s.dianping_crawler_timeout_seconds
        self.max_results = s.dianping_crawler_max_results

    def _normalize(self, data: dict[str, Any] | list, *, place_name: str, city: str | None, country: str) -> list:
        payload = data if isinstance(data, dict) else {"items": data}
        return normalize_dianping_payload(
            payload, place_name=place_name, city=city, country=country, ticket_signal=True
        )


def build_dianping_tools(settings: Settings | None = None) -> dict[str, BaseCrawlerTool]:
    s = settings or get_settings()
    return {
        "dianping_review_crawler_mcp": DianpingReviewCrawlerTool(s),
        "dianping_ticket_signal_crawler_mcp": DianpingTicketSignalCrawlerTool(s),
    }
