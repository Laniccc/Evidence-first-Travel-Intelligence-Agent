import json
import time
from hashlib import sha256
from typing import Any

from app.config import get_settings


class ToolCache:
    def __init__(self, ttl_seconds: int | None = None) -> None:
        settings = get_settings()
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.real_tool_cache_ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def _key(self, tool_name: str, payload: dict[str, Any]) -> str:
        raw = json.dumps({"tool": tool_name, **payload}, sort_keys=True, default=str)
        return sha256(raw.encode("utf-8")).hexdigest()

    def get(self, tool_name: str, **payload: Any) -> Any | None:
        key = self._key(tool_name, payload)
        item = self._store.get(key)
        if not item:
            return None
        expires_at, value = item
        if time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, tool_name: str, value: Any, **payload: Any) -> None:
        key = self._key(tool_name, payload)
        self._store[key] = (time.time() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()


_cache: ToolCache | None = None


def get_tool_cache() -> ToolCache:
    global _cache
    if _cache is None:
        _cache = ToolCache()
    return _cache
