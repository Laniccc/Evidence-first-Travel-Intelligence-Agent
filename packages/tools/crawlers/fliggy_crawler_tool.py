"""Fliggy ticket provider — Taobao TOP Open API only."""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings, get_settings
from tools.crawlers.base_crawler_tool import BaseCrawlerTool
from tools.ticketing.evidence_normalizer import normalize_fliggy_ticket_payload
from tools.ticketing.fliggy_open_api_service import FliggyOpenApiService
from tools.ticketing.provider_config import fliggy_top_api_configured
from tools.ticketing.ticket_snapshot_store import TicketSnapshotStore


class FliggyTicketSnapshotCrawlerTool(BaseCrawlerTool):
    provider_name = "Fliggy"
    policy_name = "fliggy_ticket_snapshot_crawler_mcp"

    def __init__(self, settings: Settings | None = None, snapshot_store: TicketSnapshotStore | None = None) -> None:
        super().__init__(settings)
        s = self.settings
        self.enabled = s.fliggy_ticket_crawler_enabled and s.enable_ticket_crawler_providers
        self.max_results = s.fliggy_ticket_crawler_max_results
        self._store = snapshot_store
        self._api = FliggyOpenApiService(s)

    def _store_instance(self) -> TicketSnapshotStore | None:
        if not self.settings.ticket_snapshot_store_enabled:
            return None
        if self._store is None:
            self._store = TicketSnapshotStore(self.settings.ticket_snapshot_db_path)
        return self._store

    def is_configured(self) -> bool:
        if not self.enabled:
            return False
        return fliggy_top_api_configured(self.settings)

    def _normalize(self, data: dict[str, Any] | list, *, place_name: str, city: str | None, country: str) -> list:
        payload = data if isinstance(data, dict) else {"items": data}
        evidence = normalize_fliggy_ticket_payload(
            payload, place_name=place_name, city=city, country=country, review_mode=False
        )
        store = self._store_instance()
        saved = 0
        if store:
            items = payload.get("items") or payload.get("tickets") or []
            if isinstance(items, dict):
                items = [items]
            for item in items:
                if store.save_from_item(place_name, "Fliggy", item):
                    saved += 1
        self.last_run_meta["snapshot_saved_count"] = saved
        return evidence

    async def run_query(
        self,
        place_name: str,
        city: str | None = None,
        country: str | None = None,
        query: str | None = None,
        claim_type: str | None = None,
    ) -> tuple[dict[str, Any] | list | None, str | None]:
        _ = claim_type
        if not fliggy_top_api_configured(self.settings):
            return None, "Fliggy Open API not configured"

        items, err = await asyncio.to_thread(
            self._api.fetch_ticket_items,
            place_name,
            city=city,
            country=country,
            query=query,
            max_results=self.max_results,
        )
        self.last_run_meta = {
            "provider": self.provider_name,
            "configured": self.is_configured(),
            "transport": "fliggy_top_api",
            "output_parse_status": "ok" if items and not err else "parse_error",
            "error": err,
            **self._api.last_run_meta,
        }
        if err:
            return None, err
        return {"items": items}, None


def build_fliggy_tools(
    settings: Settings | None = None,
    snapshot_store: TicketSnapshotStore | None = None,
) -> dict[str, BaseCrawlerTool]:
    s = settings or get_settings()
    return {
        "fliggy_ticket_snapshot_crawler_mcp": FliggyTicketSnapshotCrawlerTool(s, snapshot_store),
    }
