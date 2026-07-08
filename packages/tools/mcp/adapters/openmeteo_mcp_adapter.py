from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mcp.adapters.baidu_response_parser import coerce_baidu_payload
from tools.mcp.adapters.page_content_extractor import text_from_mcp_payload
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager


class OpenMeteoMCPAdapter(BaseTravelTool):
    """Open-Meteo MCP via streamable HTTP: geocoding + forecast/archive tools."""

    def __init__(self, policy_name: str, client: MCPClientManager | None = None) -> None:
        self.policy_name = policy_name
        self.name = policy_name
        self.server_name = "openmeteo"
        self._client = client or get_mcp_client_manager()

    def is_available(self) -> bool:
        return self._client.is_server_configured("openmeteo")

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason("openmeteo"))

        city = kwargs.get("city") or kwargs.get("place_name") or ""
        country = kwargs.get("country") or ""
        query = kwargs.get("query") or f"{city}, {country}".strip(", ")
        lat = kwargs.get("latitude")
        lon = kwargs.get("longitude")

        if lat is None or lon is None:
            geo = await self._client.invoke("openmeteo", "geocoding", {"name": query, "count": 1})
            if not geo.ok:
                raise RuntimeError(geo.error or "geocoding failed")
            lat, lon = self._parse_coords(geo.data)
            if lat is None or lon is None:
                raise RuntimeError(f"geocoding returned no coordinates for {query!r}")

        tool = self._select_tool()
        args: dict[str, Any] = {"latitude": lat, "longitude": lon}
        if tool == "weather_forecast":
            args["current_weather"] = True
            args["daily"] = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"]
        elif tool == "weather_archive":
            args["start_date"] = kwargs.get("start_date", "2020-01-01")
            args["end_date"] = kwargs.get("end_date", "2020-12-31")
            args["daily"] = ["temperature_2m_mean", "precipitation_sum"]

        result = await self._client.invoke("openmeteo", tool, args)
        if not result.ok:
            raise RuntimeError(result.error or f"{tool} failed")

        summary = text_from_mcp_payload(result.data)[:1200]
        claim_type = ClaimType.WEATHER
        if self.policy_name == "climate_mcp":
            claim_type = ClaimType.SEASONALITY

        return [
            Evidence(
                source_name="Open-Meteo MCP",
                source_type=SourceType.WEATHER_API,
                source_url="https://open-meteo.com/",
                country=country or "Unknown",
                city=city or None,
                place_name=kwargs.get("place_name"),
                retrieved_at=datetime.utcnow(),
                data_freshness=DataFreshness.LIVE,
                license_scope=LicenseScope.PUBLIC_PAGE,
                confidence=0.8,
                claims=[
                    Claim(
                        claim_type=claim_type,
                        value=summary,
                        raw_text=summary,
                        confidence=0.8,
                        normalized_value={"tool": tool, "latitude": lat, "longitude": lon},
                    )
                ],
                limitations=[f"Open-Meteo via {tool}; verify for travel decisions."],
            )
        ]

    def _select_tool(self) -> str:
        if self.policy_name == "climate_mcp":
            return "weather_archive"
        return "weather_forecast"

    @staticmethod
    def _parse_coords(data: Any) -> tuple[float | None, float | None]:
        data = coerce_baidu_payload(data)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return None, None
        if isinstance(data, dict):
            if "latitude" in data and "longitude" in data:
                return float(data["latitude"]), float(data["longitude"])
            for key in ("results", "data", "locations"):
                bucket = data.get(key)
                if isinstance(bucket, list) and bucket:
                    first = bucket[0]
                    if isinstance(first, dict):
                        if "latitude" in first and "longitude" in first:
                            return float(first["latitude"]), float(first["longitude"])
                        if "lat" in first and "lon" in first:
                            return float(first["lat"]), float(first["lon"])
        return None, None
