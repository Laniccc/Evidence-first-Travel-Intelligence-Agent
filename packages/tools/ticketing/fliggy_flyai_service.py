"""Fliggy AI Open Platform (flyai.open.fliggy.com) ticket/POI search."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

from app.config import Settings, get_settings
from tools.ticketing.provider_config import effective_flyai_api_key, fliggy_flyai_configured

logger = logging.getLogger(__name__)

_DEFAULT_CLI = "npx --yes @fly-ai/flyai-cli@1.0.16"


class FliggyFlyAiService:
    """Invoke @fly-ai/flyai-cli with FLYAI_API_KEY for POI / keyword ticket search."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.last_run_meta: dict[str, Any] = {}

    def is_configured(self) -> bool:
        return fliggy_flyai_configured(self.settings)

    def _cli_argv(self, subcommand: str, *args: str) -> list[str]:
        base = (self.settings.fliggy_flyai_cli_command or _DEFAULT_CLI).strip()
        return base.split() + [subcommand, *args]

    def _run_cli(self, argv: list[str]) -> tuple[dict[str, Any] | None, str | None]:
        api_key = effective_flyai_api_key(self.settings)
        if not api_key:
            return None, "Fliggy FlyAI API key not configured"
        env = os.environ.copy()
        env["FLYAI_API_KEY"] = api_key
        timeout = float(self.settings.fliggy_flyai_timeout_seconds)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return None, f"flyai-cli timeout after {timeout}s"
        except OSError as exc:
            return None, str(exc)
        raw = (proc.stdout or "").strip()
        if proc.returncode != 0:
            err = (proc.stderr or raw or "").strip()[:500]
            return None, err or f"flyai-cli exit {proc.returncode}"
        if not raw:
            return None, "flyai-cli returned empty stdout"
        try:
            return json.loads(raw), None
        except json.JSONDecodeError:
            return None, f"flyai-cli invalid JSON: {raw[:200]}"

    def fetch_ticket_items(
        self,
        place_name: str,
        city: str | None = None,
        country: str | None = None,
        query: str | None = None,
        max_results: int | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self.is_configured():
            return [], "Fliggy FlyAI not configured"
        limit = max_results or self.settings.fliggy_ticket_crawler_max_results
        keyword = (query or place_name or "").strip()
        if not keyword:
            return [], "place_name is required"

        if city:
            argv = self._cli_argv(
                "search-poi",
                "--city-name",
                city,
                "--keyword",
                keyword,
            )
            method = "search-poi"
        else:
            search_q = keyword if "门票" in keyword or "票" in keyword else f"{keyword} 门票"
            argv = self._cli_argv("keyword-search", "--query", search_q)
            method = "keyword-search"

        data, err = self._run_cli(argv)
        self.last_run_meta = {
            "api_method": method,
            "place_name": place_name,
            "city": city,
            "query": keyword,
            "error": err,
        }
        if err or data is None:
            return [], err
        if data.get("status") not in (0, "0", None) and data.get("message") not in ("success", None):
            return [], data.get("systemMessage") or data.get("message") or "flyai-cli error"

        items = flyai_response_to_items(data, max_results=limit)
        self.last_run_meta["item_count"] = len(items)
        if data.get("systemMessage"):
            self.last_run_meta["system_message"] = data["systemMessage"]
        return items, None if items else "Fliggy FlyAI returned no ticket products"


def flyai_response_to_items(response: dict[str, Any], *, max_results: int) -> list[dict[str, Any]]:
    """Normalize flyai-cli JSON (search-poi / keyword-search) to crawler item shape."""
    item_list = (response.get("data") or {}).get("itemList") or []
    items: list[dict[str, Any]] = []
    for raw in item_list:
        if not isinstance(raw, dict):
            continue
        if "name" in raw:
            ticket_info = raw.get("ticketInfo") or {}
            if not isinstance(ticket_info, dict):
                ticket_info = {}
            price_text = ticket_info.get("price")
            ticket_name = ticket_info.get("ticketName") or raw.get("name")
            free_status = raw.get("freePoiStatus")
            if not price_text and free_status == "FREE":
                price_text = "免费"
            items.append(
                {
                    "ticket_type": ticket_name,
                    "price_text": price_text,
                    "sales_status": "免费" if free_status == "FREE" else "收费",
                    "booking_channel": "Fliggy",
                    "platform_ticket_url": raw.get("jumpUrl"),
                    "scenic_name": raw.get("name"),
                    "confidence": 0.65 if price_text else 0.55,
                    "source": "fliggy_flyai_search_poi",
                }
            )
        elif "info" in raw and isinstance(raw["info"], dict):
            info = raw["info"]
            price = info.get("price")
            price_text = f"¥{price}" if price is not None else None
            items.append(
                {
                    "ticket_type": info.get("title"),
                    "price": price,
                    "price_text": price_text,
                    "booking_channel": "Fliggy",
                    "platform_ticket_url": info.get("jumpUrl"),
                    "confidence": 0.58 if price_text else 0.52,
                    "source": "fliggy_flyai_keyword_search",
                }
            )
        if len(items) >= max_results:
            break
    return items[:max_results]
