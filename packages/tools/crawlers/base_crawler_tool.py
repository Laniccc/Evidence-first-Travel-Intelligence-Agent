"""Subprocess-based local crawler wrapper base."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class BaseCrawlerTool:
    """Invoke external crawler CLI; expect JSON on stdout."""

    provider_name: str = "crawler"
    policy_name: str = "crawler_mcp"
    command: str = ""
    workdir: str | None = None
    timeout_seconds: float = 30.0
    max_results: int = 20
    enabled: bool = False

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.last_run_meta: dict[str, Any] = {}

    def is_configured(self) -> bool:
        return bool(self.enabled and (self.command or "").strip())

    def _format_command(
        self,
        place_name: str,
        city: str | None,
        country: str | None,
        query: str | None,
        claim_type: str | None,
    ) -> list[str]:
        cmd = self.command
        replacements = {
            "{place}": place_name or "",
            "{city}": city or "",
            "{country}": country or "",
            "{query}": query or place_name or "",
            "{claim_type}": claim_type or "",
        }
        for key, val in replacements.items():
            cmd = cmd.replace(key, val)
        return cmd.split()

    def _run_subprocess(
        self,
        place_name: str,
        city: str | None = None,
        country: str | None = None,
        query: str | None = None,
        claim_type: str | None = None,
    ) -> tuple[dict[str, Any] | list | None, str | None]:
        if not self.is_configured():
            return None, "crawler not configured (empty command or disabled)"
        argv = self._format_command(place_name, city, country, query, claim_type)
        payload = {
            "place_name": place_name,
            "city": city,
            "country": country,
            "query": query or place_name,
            "claim_type": claim_type,
            "max_results": self.max_results,
        }
        try:
            proc = subprocess.run(
                argv,
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=self.workdir or None,
            )
        except subprocess.TimeoutExpired:
            return None, f"crawler timeout after {self.timeout_seconds}s"
        except OSError as exc:
            return None, str(exc)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:500]
            return None, err or f"crawler exit {proc.returncode}"
        raw = (proc.stdout or "").strip()
        if not raw:
            return None, "crawler returned empty stdout"
        try:
            return json.loads(raw), None
        except json.JSONDecodeError:
            return {"items": [{"review_summary": raw[:500], "confidence": 0.4}]}, None

    async def run_query(
        self,
        place_name: str,
        city: str | None = None,
        country: str | None = None,
        query: str | None = None,
        claim_type: str | None = None,
    ) -> tuple[dict[str, Any] | list | None, str | None]:
        data, err = self._run_subprocess(place_name, city, country, query, claim_type)
        self.last_run_meta = {
            "provider": self.provider_name,
            "configured": self.is_configured(),
            "crawler_command": self.command,
            "error": err,
        }
        return data, err

    async def run(
        self,
        place_name: str | None = None,
        city: str | None = None,
        country: str | None = "China",
        query: str | None = None,
        claim_type: str | None = None,
        **kwargs: Any,
    ) -> list:
        from app.schemas.evidence import Evidence

        data, err = await self.run_query(
            place_name or "",
            city=city,
            country=country,
            query=query,
            claim_type=claim_type or kwargs.get("information_need"),
        )
        if err or data is None:
            self.last_run_meta["error"] = err
            return []
        return self._normalize(data, place_name=place_name or "", city=city, country=country or "China")

    def _normalize(
        self,
        data: dict[str, Any] | list,
        *,
        place_name: str,
        city: str | None,
        country: str,
    ) -> list:
        raise NotImplementedError
