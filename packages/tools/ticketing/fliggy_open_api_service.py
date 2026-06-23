"""High-level Fliggy ticket lookup via Open Platform APIs."""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings
from tools.ticketing.fliggy_open_api_client import (
    FliggyOpenApiClient,
    scenic_query_response_to_items,
    scenics_get_response_to_items,
)
from tools.ticketing.provider_config import fliggy_top_api_configured

logger = logging.getLogger(__name__)


class FliggyOpenApiService:
    """Search scenic/ticket products by place name (TOP APIs)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = FliggyOpenApiClient(self.settings)
        self.last_run_meta: dict[str, Any] = {}

    def is_configured(self) -> bool:
        return fliggy_top_api_configured(self.settings)

    def fetch_ticket_items(
        self,
        place_name: str,
        city: str | None = None,
        country: str | None = None,
        query: str | None = None,
        max_results: int | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self.is_configured():
            return [], "Fliggy Open API not configured"
        scenic_name = (query or place_name or "").strip()
        if not scenic_name:
            return [], "place_name is required"

        limit = max_results or self.settings.fliggy_ticket_crawler_max_results
        biz: dict[str, Any] = {"scenic": scenic_name}
        if city:
            biz["city"] = city

        data, err = self._client.execute("taobao.alitrip.travel.baseinfo.scenics.get", biz)
        self.last_run_meta = {
            "api_method": "taobao.alitrip.travel.baseinfo.scenics.get",
            "scenic": scenic_name,
            "city": city,
            "error": err,
        }
        if err or data is None:
            return [], err

        items = scenics_get_response_to_items(data, max_results=limit)
        if items:
            self.last_run_meta["item_count"] = len(items)
            return items, None

        if self.settings.fliggy_session:
            scenic_id = self._first_scenic_id(data)
            if scenic_id is not None:
                enriched, enrich_err = self._fetch_scenic_tickets(scenic_id, limit)
                if enriched:
                    self.last_run_meta["api_method"] = "alitrip.ticket.scenic.query"
                    self.last_run_meta["ali_scenic_id"] = scenic_id
                    self.last_run_meta["item_count"] = len(enriched)
                    return enriched, None
                if enrich_err:
                    return [], enrich_err

        return [], "Fliggy scenic search returned no ticket products"

    def _first_scenic_id(self, scenics_response: dict[str, Any]) -> int | str | None:
        root = scenics_response.get("alitrip_travel_baseinfo_scenics_get_response") or scenics_response
        scenic_list = root.get("scenic_list") or {}
        scenics = scenic_list.get("scenic_info") or scenic_list.get("scenics") or scenic_list.get("scenic")
        if isinstance(scenics, dict):
            scenics = [scenics]
        if not scenics:
            return None
        first = scenics[0]
        if not isinstance(first, dict):
            return None
        return first.get("scenic_id") or first.get("ali_scenic_id")

    def _fetch_scenic_tickets(
        self,
        ali_scenic_id: int | str,
        max_results: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        data, err = self._client.execute(
            "alitrip.ticket.scenic.query",
            {"ali_scenic_id": str(ali_scenic_id), "current_page": "1"},
        )
        if err or data is None:
            return [], err
        return scenic_query_response_to_items(data, max_results=max_results), None
