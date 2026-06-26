"""Fliggy ticket provider — FlyAI (primary), TOP API, subprocess fallback."""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings, get_settings
from tools.crawlers.base_crawler_tool import BaseCrawlerTool
from tools.ticketing.evidence_normalizer import normalize_fliggy_ticket_payload
from tools.ticketing.fliggy_flyai_service import FliggyFlyAiService
from tools.ticketing.fliggy_open_api_service import FliggyOpenApiService
from tools.ticketing.provider_config import (
    fliggy_crawler_configured,
    fliggy_flyai_configured,
    fliggy_subprocess_configured,
    fliggy_ticket_api_enabled,
    fliggy_top_api_configured,
)
from tools.ticketing.ticket_snapshot_store import TicketSnapshotStore


class FliggyTicketSnapshotCrawlerTool(BaseCrawlerTool):
    provider_name = "Fliggy"
    policy_name = "fliggy_ticket_api_mcp"

    def __init__(self, settings: Settings | None = None, snapshot_store: TicketSnapshotStore | None = None) -> None:
        super().__init__(settings)
        s = self.settings
        self.enabled = s.fliggy_ticket_crawler_enabled and s.enable_ticket_crawler_providers
        self.max_results = s.fliggy_ticket_api_max_results or s.fliggy_ticket_crawler_max_results
        self.command = s.fliggy_ticket_crawler_command or ""
        self.workdir = s.fliggy_ticket_crawler_workdir or None
        self.timeout_seconds = s.fliggy_ticket_crawler_timeout_seconds
        self._store = snapshot_store
        self._flyai = FliggyFlyAiService(s)
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
        return fliggy_crawler_configured(self.settings)

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
        aliases: list[str] | None = None,
        province: str | None = None,
        visit_date: str | None = None,
        normalized_place_id: str | None = None,
        baidu_uid: str | None = None,
    ) -> tuple[dict[str, Any] | list | None, str | None]:
        _ = (claim_type, province, visit_date, normalized_place_id, baidu_uid, country)
        if not self.is_configured():
            return None, "Fliggy not configured"

        search_terms: list[str] = []
        for term in [query, place_name, *(aliases or [])]:
            text = str(term or "").strip()
            if text and text not in search_terms:
                search_terms.append(text)

        items: list[dict[str, Any]] = []
        last_err: str | None = None
        transport = "unknown"

        if fliggy_flyai_configured(self.settings):
            transport = "fliggy_flyai_cli"
            for term in search_terms[:6]:
                batch, err = await asyncio.to_thread(
                    self._flyai.fetch_ticket_items,
                    term,
                    city=city,
                    query=term,
                    aliases=aliases,
                    max_results=self.max_results,
                )
                last_err = err
                if batch:
                    items.extend(batch)
                    break
            self.last_run_meta.update(self._flyai.last_run_meta)

        if not items and fliggy_top_api_configured(self.settings):
            transport = "fliggy_top_api"
            for term in search_terms[:6]:
                batch, err = await asyncio.to_thread(
                    self._api.fetch_ticket_items,
                    term,
                    city=city,
                    country=country,
                    query=term,
                    max_results=self.max_results,
                )
                last_err = err
                if batch:
                    items.extend(batch)
                    break
            self.last_run_meta.update(self._api.last_run_meta)

        if not items and fliggy_subprocess_configured(self.settings):
            transport = "fliggy_subprocess"
            data, err = await asyncio.to_thread(
                self.run_subprocess,
                place_name,
                city=city,
                country=country,
                query=query or place_name,
                claim_type=claim_type,
            )
            last_err = err
            if isinstance(data, dict):
                raw_items = data.get("items") or []
                if isinstance(raw_items, list):
                    items.extend(raw_items)

        self.last_run_meta.update(
            {
                "provider": self.provider_name,
                "configured": self.is_configured(),
                "transport": transport,
                "aliases_tried": search_terms[:6],
                "output_parse_status": "ok" if items else "parse_error",
                "error": last_err,
            }
        )
        if not items:
            return None, last_err or "Fliggy returned no ticket products"
        return {"items": items[: self.max_results]}, None


def build_fliggy_tools(
    settings: Settings | None = None,
    snapshot_store: TicketSnapshotStore | None = None,
) -> dict[str, BaseCrawlerTool]:
    s = settings or get_settings()
    tool = FliggyTicketSnapshotCrawlerTool(s, snapshot_store)
    return {
        "fliggy_ticket_api_mcp": tool,
        "fliggy_ticket_snapshot_crawler_mcp": tool,
    }
