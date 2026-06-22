from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mcp.adapters.page_content_extractor import text_from_mcp_payload
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager


def _format_address(city: str | None, country: str | None, place_name: str | None) -> str:
    parts = [p for p in (place_name, city, country) if p]
    return ", ".join(parts)


class OsmMCPAdapter(BaseTravelTool):
    """OSM MCP stdio adapter — geocode_address, find_nearby_places, etc."""

    def __init__(self, policy_name: str, client: MCPClientManager | None = None) -> None:
        self.policy_name = policy_name
        self.name = policy_name
        self.server_name = "osm"
        self._client = client or get_mcp_client_manager()

    def is_available(self) -> bool:
        return self._client.is_server_configured("osm")

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason("osm"))

        address = kwargs.get("address") or _format_address(
            kwargs.get("city"), kwargs.get("country"), kwargs.get("place_name")
        )
        tool, args = self._build_invoke(kwargs, address)
        result = await self._client.invoke("osm", tool, args)
        if not result.ok:
            raise RuntimeError(result.error or f"osm/{tool} failed")

        text = text_from_mcp_payload(result.data)
        claim_type = ClaimType.ADDRESS
        if self.policy_name in {"places_mcp"} and kwargs.get("information_need") == "nearby_food":
            claim_type = ClaimType.FOOD

        return [
            Evidence(
                source_name="OpenStreetMap MCP",
                source_type=SourceType.MAP,
                source_url="https://www.openstreetmap.org/",
                country=kwargs.get("country") or "Unknown",
                city=kwargs.get("city"),
                place_name=kwargs.get("place_name"),
                retrieved_at=datetime.utcnow(),
                data_freshness=DataFreshness.RECENT,
                license_scope=LicenseScope.PUBLIC_PAGE,
                confidence=0.78,
                claims=[
                    Claim(
                        claim_type=claim_type,
                        value=text[:800],
                        raw_text=text[:2000],
                        confidence=0.78,
                        normalized_value={"osm_tool": tool},
                    )
                ],
                limitations=[f"OSM via {tool}."],
            )
        ]

    def _build_invoke(self, kwargs: dict[str, Any], address: str) -> tuple[str, dict[str, Any]]:
        if self.policy_name == "geocode_mcp":
            if kwargs.get("latitude") is not None and kwargs.get("longitude") is not None:
                return "reverse_geocode", {
                    "latitude": float(kwargs["latitude"]),
                    "longitude": float(kwargs["longitude"]),
                }
            return "geocode_address", {"address": address}

        if self.policy_name == "places_mcp":
            lat = kwargs.get("latitude")
            lon = kwargs.get("longitude")
            if lat is None or lon is None:
                return "geocode_address", {"address": address}
            category = "restaurant" if kwargs.get("information_need") in {"nearby_food", "nearby_rest_area"} else "tourism"
            return "find_nearby_places", {
                "latitude": float(lat),
                "longitude": float(lon),
                "radius": int(kwargs.get("radius") or 1000),
                "category": category,
            }

        if kwargs.get("latitude") is not None and kwargs.get("longitude") is not None:
            return "explore_area", {
                "latitude": float(kwargs["latitude"]),
                "longitude": float(kwargs["longitude"]),
            }
        return "geocode_address", {"address": address}
