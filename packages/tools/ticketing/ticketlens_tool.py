"""TicketLens Experiences REST provider."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.config import Settings, get_settings
from tools.ticketing.evidence_normalizer import normalize_ticketlens_items
from tools.ticketing.provider_config import ticketlens_configured
from tools.ticketing.ticket_snapshot_store import TicketSnapshotStore

logger = logging.getLogger(__name__)


class TicketLensExperienceTool:
    policy_name = "ticketlens_experience_mcp"
    provider_name = "TicketLens"

    def __init__(self, settings: Settings | None = None, snapshot_store: TicketSnapshotStore | None = None) -> None:
        self.settings = settings or get_settings()
        self._store = snapshot_store
        self.last_run_meta: dict[str, Any] = {}

    def is_configured(self) -> bool:
        return ticketlens_configured(self.settings)

    def _store_instance(self) -> TicketSnapshotStore | None:
        if not self.settings.ticket_snapshot_store_enabled:
            return None
        if self._store is None:
            self._store = TicketSnapshotStore(self.settings.ticket_snapshot_db_path)
        return self._store

    def _fetch_experiences(
        self,
        place_name: str,
        city: str | None,
        country: str | None,
        query: str | None,
        travel_date: str | None,
        max_results: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self.is_configured():
            return [], "TicketLens not configured"
        base = (self.settings.ticketlens_api_base_url or "").rstrip("/")
        params = {
            "q": query or place_name,
            "place": place_name,
            "city": city or "",
            "country": country or "China",
            "limit": max_results,
        }
        if travel_date:
            params["date"] = travel_date
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v)
        url = f"{base}/experiences/search?{qs}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.ticketlens_api_key}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.settings.ticketlens_timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
            items = data.get("items") or data.get("experiences") or data.get("results") or []
            if isinstance(items, dict):
                items = [items]
            return items, None
        except urllib.error.HTTPError as exc:
            return [], f"TicketLens HTTP {exc.code}: {exc.reason}"
        except Exception as exc:
            return [], str(exc)

    async def run(
        self,
        place_name: str | None = None,
        city: str | None = None,
        country: str | None = "China",
        query: str | None = None,
        travel_date: str | None = None,
        max_results: int = 10,
        mode: str = "ticket",
        **kwargs: Any,
    ) -> list:
        items, err = self._fetch_experiences(
            place_name or "",
            city,
            country,
            query,
            travel_date,
            max_results,
        )
        self.last_run_meta = {
            "provider": self.provider_name,
            "configured": self.is_configured(),
            "error": err,
            "output_parse_status": "ok" if items and not err else "parse_error",
        }
        if err:
            return []
        evidence = normalize_ticketlens_items(
            items,
            place_name=place_name or "",
            city=city,
            country=country or "China",
            mode=mode,
        )
        store = self._store_instance()
        saved = 0
        if store:
            for item in items:
                if store.save_from_item(place_name or "", "TicketLens", item):
                    saved += 1
        self.last_run_meta["snapshot_saved_count"] = saved
        return evidence


class TicketLensReviewSignalTool(TicketLensExperienceTool):
    policy_name = "ticketlens_experience_review_signal_mcp"

    async def run(self, **kwargs: Any) -> list:
        kwargs["mode"] = "review"
        return await super().run(**kwargs)


class TicketSnapshotStoreTool:
    policy_name = "ticket_snapshot_store"
    provider_name = "ticket_snapshot_store"

    def __init__(self, settings: Settings | None = None, store: TicketSnapshotStore | None = None) -> None:
        self.settings = settings or get_settings()
        self._store = store
        self.last_run_meta: dict[str, Any] = {}

    def is_configured(self) -> bool:
        return bool(self.settings.ticket_snapshot_store_enabled)

    def _store_instance(self) -> TicketSnapshotStore:
        if self._store is None:
            self._store = TicketSnapshotStore(self.settings.ticket_snapshot_db_path)
        return self._store

    async def run(
        self,
        place_name: str | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> list:
        from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType

        if not place_name:
            return []
        snap = self._store_instance().query_latest(place_name, provider)
        if not snap:
            return []
        claims = [
            Claim(
                claim_type=ClaimType.HISTORICAL_TICKET_SNAPSHOT,
                value=snap.price_text or str(snap.price),
                confidence=0.6,
            ),
            Claim(
                claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                value=snap.price_text or str(snap.price),
                confidence=0.5,
            ),
        ]
        return [
            Evidence(
                source_name="TicketSnapshotStore",
                source_type=SourceType.TICKET_PLATFORM,
                source_url=snap.source_url,
                country=kwargs.get("country") or "China",
                place_name=place_name,
                confidence=0.55,
                claims=claims,
                limitations=["历史快照仅供参考，不能替代当前实时票价。"],
            )
        ]


class TicketPriceHistoryQueryTool:
    policy_name = "ticket_price_history_query"
    provider_name = "ticket_price_history_query"

    def __init__(self, settings: Settings | None = None, store: TicketSnapshotStore | None = None) -> None:
        self.settings = settings or get_settings()
        self._store = store
        self.last_run_meta: dict[str, Any] = {}

    def is_configured(self) -> bool:
        return bool(self.settings.ticket_snapshot_store_enabled)

    def _store_instance(self) -> TicketSnapshotStore:
        if self._store is None:
            self._store = TicketSnapshotStore(self.settings.ticket_snapshot_db_path)
        return self._store

    async def run(
        self,
        place_name: str | None = None,
        provider: str | None = None,
        since: str | None = None,
        **kwargs: Any,
    ) -> list:
        from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType

        if not place_name:
            return []
        history = self._store_instance().query_history(place_name, provider=provider, since=since)
        if not history:
            return []
        claims = [
            Claim(
                claim_type=ClaimType.TICKET_PRICE_HISTORY,
                value=f"{h.provider}:{h.price_text or h.price}@{h.captured_at}",
                confidence=0.6,
            )
            for h in history[:10]
        ]
        return [
            Evidence(
                source_name="TicketSnapshotStore",
                source_type=SourceType.TICKET_PLATFORM,
                country=kwargs.get("country") or "China",
                place_name=place_name,
                confidence=0.6,
                claims=claims,
                limitations=["历史票价来自本地快照库，不代表当前官方售价。"],
            )
        ]
