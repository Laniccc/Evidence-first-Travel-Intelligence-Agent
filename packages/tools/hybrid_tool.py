import asyncio
import logging
from datetime import datetime
from typing import Any

from app.config import Settings, get_settings
from app.schemas.evidence import Evidence
from app.storage.tool_cache import get_tool_cache
from tools.base import BaseTravelTool

logger = logging.getLogger(__name__)


class HybridTravelTool(BaseTravelTool):
    """Runs real tool first (hybrid/real mode), falls back to mock on failure or missing key."""

    def __init__(
        self,
        name: str,
        real_tool: BaseTravelTool | None,
        mock_tool: BaseTravelTool,
        settings: Settings | None = None,
        real_enabled: bool = True,
        requires_api_key: bool = True,
        allow_mock_fallback: bool | None = None,
    ) -> None:
        self.name = name
        self.real_tool = real_tool
        self.mock_tool = mock_tool
        self.settings = settings or get_settings()
        self.real_enabled = real_enabled
        self.requires_api_key = requires_api_key
        if allow_mock_fallback is None:
            allow_mock_fallback = self.settings.tool_mode == "hybrid"
        self.allow_mock_fallback = allow_mock_fallback
        self.last_run_meta: dict[str, Any] = {}

    def real_is_available(self) -> bool:
        if not self.real_enabled or self.real_tool is None:
            return False
        if self.settings.tool_mode == "mock":
            return False
        if hasattr(self.real_tool, "is_available"):
            return bool(self.real_tool.is_available())
        return True

    def _should_try_real(self) -> bool:
        mode = self.settings.tool_mode
        if mode == "mock":
            return False
        if mode == "real":
            return self.real_is_available()
        return self.real_is_available()

    async def run(self, **kwargs) -> list[Evidence]:
        self.last_run_meta = {
            "fallback_used": False,
            "cache_hit": False,
            "primary_tool": self.real_tool.name if self.real_tool else None,
            "fallback_tools": [self.mock_tool.name],
        }
        cache = get_tool_cache()
        cache_payload = self._cache_payload(kwargs)
        cached = cache.get(self.name, **cache_payload)
        if cached is not None:
            self.last_run_meta["cache_hit"] = True
            return [ev.model_copy(deep=True) for ev in cached]

        if self._should_try_real() and self.real_tool is not None:
            try:
                result = await asyncio.wait_for(
                    self.real_tool.run(**kwargs),
                    timeout=self.settings.real_tool_timeout_seconds,
                )
                if result:
                    cache.set(self.name, result, **cache_payload)
                    return result
                self.last_run_meta["real_empty"] = True
            except Exception as exc:
                logger.warning("Real tool %s failed: %s", self.name, exc)
                self.last_run_meta["real_error"] = str(exc)

        if not self.allow_mock_fallback:
            return []

        self.last_run_meta["fallback_used"] = True
        result = await self.mock_tool.run(**kwargs)
        for ev in result:
            if "fallback_used=true" not in ev.limitations:
                ev.limitations.append("fallback_used=true")
            ev.limitations.append(f"Real tool unavailable or failed; used {self.mock_tool.name}.")
        return result

    def _cache_payload(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {
            "place": kwargs.get("place_name") or kwargs.get("place"),
            "city": kwargs.get("city"),
            "country": kwargs.get("country"),
            "date": kwargs.get("travel_date") or kwargs.get("date"),
            "need_type": kwargs.get("need_type"),
        }


def annotate_evidence_retrieved_at(evidence: list[Evidence]) -> list[Evidence]:
    now = datetime.utcnow()
    for ev in evidence:
        ev.retrieved_at = now
    return evidence
