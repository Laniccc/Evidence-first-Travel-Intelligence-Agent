import logging
from typing import Any, Callable, Awaitable

from pydantic import ValidationError

from app.config import get_settings
from app.schemas.evidence import Evidence
from app.tools.base import BaseTravelTool

logger = logging.getLogger(__name__)


class MCPToolAdapter(BaseTravelTool):
    """Wraps MCP server responses into validated Evidence objects."""

    name = "mcp_tool_adapter"
    mcp_tool_name: str = "generic_mcp"
    capabilities: list[str] = []

    def __init__(
        self,
        mcp_tool_name: str,
        capabilities: list[str],
        invoke: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        self.mcp_tool_name = mcp_tool_name
        self.name = mcp_tool_name
        self.capabilities = capabilities
        self._invoke = invoke

    def is_available(self) -> bool:
        return bool(get_settings().mcp_enabled)

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError("MCP_ENABLED=false")

        raw = await self._call_mcp(**kwargs)
        return self._normalize_to_evidence(raw, **kwargs)

    async def _call_mcp(self, **kwargs) -> Any:
        if self._invoke is not None:
            return await self._invoke(**kwargs)
        raise RuntimeError(f"MCP tool {self.mcp_tool_name} not configured (placeholder)")

    def _normalize_to_evidence(self, raw: Any, **kwargs) -> list[Evidence]:
        if isinstance(raw, list):
            evidence_list: list[Evidence] = []
            for item in raw:
                if isinstance(item, Evidence):
                    evidence_list.append(item)
                elif isinstance(item, dict):
                    evidence_list.append(Evidence.model_validate(item))
                else:
                    raise ValueError(f"Unsupported MCP payload type: {type(item)}")
            return evidence_list
        if isinstance(raw, Evidence):
            return [raw]
        if isinstance(raw, dict):
            if "evidence" in raw:
                return self._normalize_to_evidence(raw["evidence"], **kwargs)
            return [Evidence.model_validate(raw)]
        raise ValueError("MCP response must be Evidence-compatible dict or list")


class WeatherMCPAdapter(MCPToolAdapter):
    def __init__(self, invoke: Callable[..., Awaitable[Any]] | None = None) -> None:
        super().__init__(
            mcp_tool_name="weather_mcp",
            capabilities=["weather", "weather_risk"],
            invoke=invoke,
        )


class PlacesMCPAdapter(MCPToolAdapter):
    def __init__(self, invoke: Callable[..., Awaitable[Any]] | None = None) -> None:
        super().__init__(
            mcp_tool_name="places_mcp",
            capabilities=["address", "nearby_poi", "opening_status", "accessibility_proxy"],
            invoke=invoke,
        )


class OfficialReaderMCPAdapter(MCPToolAdapter):
    def __init__(self, invoke: Callable[..., Awaitable[Any]] | None = None) -> None:
        super().__init__(
            mcp_tool_name="official_reader_mcp",
            capabilities=["opening_hours", "ticket_price", "reservation_policy", "temporary_closure"],
            invoke=invoke,
        )


def validate_mcp_evidence(payload: dict) -> Evidence:
    try:
        return Evidence.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"MCP evidence schema validation failed: {exc}") from exc
