"""Shared transport selection: built-in websearch signal vs subprocess CLI."""

from __future__ import annotations

from typing import Any, Literal

from tools.ticketing.platform_websearch_signal_service import PlatformWebSearchSignalService

PlatformName = Literal["ctrip", "dianping"]


class PlatformSignalCrawlerMixin:
    """Mixin for Ctrip/Dianping crawler tools."""

    platform: PlatformName
    websearch_flag_attr: str

    def _init_platform_signal(self) -> None:
        self._websearch = PlatformWebSearchSignalService(self.settings)

    def _subprocess_configured(self) -> bool:
        return bool((self.command or "").strip())

    def _websearch_enabled(self) -> bool:
        return bool(getattr(self.settings, self.websearch_flag_attr, True))

    def _websearch_configured(self) -> bool:
        return self._websearch_enabled() and self._websearch.is_available()

    def is_configured(self) -> bool:
        if not self.enabled:
            return False
        return self._subprocess_configured() or self._websearch_configured()

    @staticmethod
    def _websearch_parse_status(meta: dict[str, Any], *, has_items: bool) -> str:
        if has_items:
            return "ok"
        if meta.get("partial_failures"):
            return "search_engine_error"
        raw_hits = int(meta.get("raw_hit_count") or 0)
        filtered = int(meta.get("filtered_hit_count") or 0)
        if raw_hits > 0 and filtered > 0:
            return "filtered_empty"
        return "no_hits"

    async def run_query(
        self,
        place_name: str,
        city: str | None = None,
        country: str | None = None,
        query: str | None = None,
        claim_type: str | None = None,
    ) -> tuple[dict[str, Any] | list | None, str | None]:
        ticket_focus = bool(
            claim_type in {"ticket_price", "ticket_price_candidate"}
            or getattr(self, "policy_name", "").endswith("ticket_signal_crawler_mcp")
        )
        signal_mode = getattr(self, "crawler_mode", None)
        if self._subprocess_configured():
            data, err = await super().run_query(  # type: ignore[misc]
                place_name,
                city,
                country,
                query,
                claim_type,
            )
            self.last_run_meta["transport"] = "subprocess_crawler"
            return data, err

        if self._websearch_configured():
            items, err = await self._websearch.fetch_signal_items(
                self.platform,
                place_name,
                city,
                query=query,
                ticket_focus=ticket_focus,
                signal_mode=signal_mode,
                max_results=self.max_results,
            )
            ws_meta = self._websearch.last_run_meta
            parse_status = self._websearch_parse_status(ws_meta, has_items=bool(items))
            self.last_run_meta = {
                "provider": self.provider_name,
                "configured": self.is_configured(),
                "transport": "platform_websearch",
                "output_parse_status": parse_status,
                "error": err,
                **ws_meta,
            }
            if err:
                return None, err
            return {"items": items}, None

        return None, "crawler not configured (enable websearch signal or set *_CRAWLER_COMMAND)"
