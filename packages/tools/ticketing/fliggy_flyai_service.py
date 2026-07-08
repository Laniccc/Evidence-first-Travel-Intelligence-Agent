"""Fliggy AI Open Platform (flyai.open.fliggy.com) via @fly-ai/flyai-cli."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

from app.config import Settings, get_settings
from tools.subprocess_argv import resolve_executable_argv
from tools.ticketing.provider_config import effective_flyai_api_key, fliggy_flyai_configured

logger = logging.getLogger(__name__)


class FliggyFlyAiService:
    """Invoke flyai-cli search-poi / keyword-search with FLYAI_API_KEY."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.last_run_meta: dict[str, Any] = {}

    def is_configured(self) -> bool:
        return fliggy_flyai_configured(self.settings)

    def fetch_ticket_items(
        self,
        place_name: str,
        *,
        city: str | None = None,
        query: str | None = None,
        aliases: list[str] | None = None,
        max_results: int | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self.is_configured():
            return [], "Fliggy FlyAI not configured"

        limit = max_results or self.settings.fliggy_ticket_crawler_max_results
        terms: list[str] = []
        for term in [query, place_name, *(aliases or [])]:
            text = str(term or "").strip()
            if text and text not in terms:
                terms.append(text)

        items: list[dict[str, Any]] = []
        last_err: str | None = None
        for term in terms[:6]:
            if city:
                data, err = self._run_cli(
                    "search-poi",
                    ["--city-name", city, "--keyword", term],
                )
            else:
                data, err = self._run_cli(
                    "keyword-search",
                    ["--query", f"{term} 门票"],
                )
            last_err = err
            if data:
                items.extend(_flyai_payload_to_items(data, term))
            if len(items) >= limit:
                break

        self.last_run_meta = {
            "api_method": "flyai-cli",
            "aliases_tried": terms[:6],
            "item_count": len(items[:limit]),
            "error": last_err,
        }
        if not items:
            return [], last_err or "FlyAI returned no ticket/POI items"
        return items[:limit], None

    def _run_cli(self, subcommand: str, args: list[str]) -> tuple[dict[str, Any] | None, str | None]:
        cmd = (self.settings.fliggy_flyai_cli_command or "npx --yes @fly-ai/flyai-cli@1.0.16").strip()
        argv = resolve_executable_argv(cmd.split()) + [subcommand, *args]
        env = os.environ.copy()
        key = effective_flyai_api_key(self.settings)
        if key:
            env["FLYAI_API_KEY"] = key
        env.setdefault("PYTHONIOENCODING", "utf-8")
        timeout = float(self.settings.fliggy_flyai_timeout_seconds or 30.0)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
                cwd=self.settings.fliggy_ticket_crawler_workdir or None,
            )
        except subprocess.TimeoutExpired:
            return None, f"flyai-cli {subcommand} timed out"
        except OSError as exc:
            return None, f"flyai-cli launch failed: {exc}"

        raw = (proc.stdout or "").strip()
        if not raw:
            if proc.returncode != 0:
                err = (proc.stderr or f"exit {proc.returncode}").strip()[:400]
                return None, err
            return None, "flyai-cli returned empty stdout"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            if proc.returncode != 0:
                err = (proc.stderr or raw or f"exit {proc.returncode}").strip()[:400]
                return None, err
            return None, "flyai-cli returned non-JSON stdout"
        if payload.get("status") not in (0, None) and payload.get("message") not in ("success", None):
            return None, str(payload.get("message") or payload.get("systemMessage") or "flyai error")
        if proc.returncode != 0:
            err = (proc.stderr or f"exit {proc.returncode}").strip()[:400]
            return payload, err or f"flyai-cli exited {proc.returncode} after returning JSON"
        return payload, None


def _flyai_payload_to_items(payload: dict[str, Any], query_term: str) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    raw_list = data.get("itemList") or data.get("items") or []
    out: list[dict[str, Any]] = []
    for row in raw_list:
        if not isinstance(row, dict):
            continue
        info = row.get("info") if isinstance(row.get("info"), dict) else row
        title = str(info.get("title") or info.get("name") or "").strip()
        if not title:
            continue
        ticket_info = info.get("ticketInfo") if isinstance(info.get("ticketInfo"), dict) else None
        price = info.get("price")
        price_text = info.get("priceText") or info.get("price_text")
        ticket_name = None
        if ticket_info:
            price = price if price is not None else ticket_info.get("price")
            price_text = price_text or ticket_info.get("priceText") or ticket_info.get("price")
            ticket_name = ticket_info.get("ticketName") or ticket_info.get("name")
        if price is not None and not price_text:
            price_text = f"{price}元"
        url = info.get("jumpUrl") or info.get("url") or row.get("jumpUrl")
        item: dict[str, Any] = {
            "ticket_title": title,
            "ticket_name": str(ticket_name).strip() if ticket_name else None,
            "ticket_type": str(ticket_name or title),
            "booking_channel": "Fliggy",
            "platform_ticket_url": url,
            "url": url,
            "confidence": 0.62 if price_text else 0.55,
            "raw_query": query_term,
            "source": "fliggy_flyai_cli",
        }
        if price_text:
            item["price_text"] = str(price_text)
        elif ticket_info:
            item["price_text"] = str(ticket_info)
        elif "门票" in title:
            item["price_text"] = title
        out.append(item)
    return out
