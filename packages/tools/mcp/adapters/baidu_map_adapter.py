from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mcp.adapters.baidu_response_parser import (
    detail_claims,
    parse_place_details,
    parse_search_places,
    parse_weather,
    pick_baidu_uid_from_evidence,
    search_claims,
    weather_claims,
)
from tools.mcp.adapters.page_content_extractor import text_from_mcp_payload
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager

_SEARCH_LIMITATIONS = [
    "百度地图地点检索结果用于地点解析和消歧，不等同于官方景区公告。",
]
_DETAIL_LIMITATIONS = [
    "地点详情字段因 POI 类型不同可能不完整；票价和开放时间仍建议以官方页面为准。",
]
_WEATHER_LIMITATIONS = [
    "天气数据用于短期出行判断，不代表长期气候规律。",
]


class BaiduMapMCPAdapter(BaseTravelTool):
    """Baidu Map MCP — map_search_places, map_place_details, map_weather."""

    def __init__(self, policy_name: str, client: MCPClientManager | None = None) -> None:
        self.policy_name = policy_name
        self.name = policy_name
        self.server_name = "baidu_map"
        self._client = client or get_mcp_client_manager()

    def is_available(self) -> bool:
        return self._client.is_server_configured("baidu_map")

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason("baidu_map"))

        if self.policy_name == "baidu_place_search_mcp":
            return await self._run_search(kwargs)
        if self.policy_name == "baidu_place_detail_mcp":
            return await self._run_detail(kwargs)
        if self.policy_name == "baidu_weather_mcp":
            return await self._run_weather(kwargs)
        raise ValueError(f"Unknown Baidu policy {self.policy_name!r}")

    async def _run_search(self, kwargs: dict[str, Any]) -> list[Evidence]:
        query = kwargs.get("query") or kwargs.get("place_name") or ""
        if not query:
            raise ValueError("baidu_place_search_mcp requires query or place_name")

        region = kwargs.get("region") or kwargs.get("city") or kwargs.get("province")
        args: dict[str, Any] = {"query": str(query)}
        if region:
            args["region"] = str(region)

        result = await self._client.invoke("baidu_map", "map_search_places", args)
        if not result.ok:
            raise RuntimeError(result.error or "map_search_places failed")

        candidates = parse_search_places(result.data)
        if not candidates and kwargs.get("city"):
            geo = await self._client.invoke(
                "baidu_map",
                "map_geocode",
                {"address": f"{query}, {kwargs.get('city')}, {kwargs.get('country') or 'China'}"},
            )
            if geo.ok:
                candidates = parse_search_places(geo.data) or [
                    {"name": query, "address": text_from_mcp_payload(geo.data)[:200]}
                ]

        if not candidates:
            text = text_from_mcp_payload(result.data)
            if text.strip():
                return [
                    self._evidence(
                        claims=[Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=text[:600], confidence=0.55)],
                        kwargs=kwargs,
                        limitations=_SEARCH_LIMITATIONS + ["Structured POI parse failed; raw text only."],
                    )
                ]
            raise RuntimeError("map_search_places returned no candidates")

        claims = search_claims(candidates)
        city = candidates[0].get("city") or kwargs.get("city")
        return [
            self._evidence(
                claims=claims,
                kwargs=kwargs,
                city=city,
                place_name=candidates[0].get("name") or kwargs.get("place_name"),
                confidence=0.72 if len(candidates) == 1 else 0.62,
                limitations=_SEARCH_LIMITATIONS,
            )
        ]

    async def _run_detail(self, kwargs: dict[str, Any]) -> list[Evidence]:
        uid = kwargs.get("uid") or kwargs.get("poi_uid")
        if not uid:
            prior = kwargs.get("prior_evidence") or kwargs.get("evidence") or []
            if isinstance(prior, list):
                uid = pick_baidu_uid_from_evidence(prior)
        if not uid:
            raise ValueError("baidu_place_detail_mcp requires uid from search or kwargs")

        result = await self._client.invoke("baidu_map", "map_place_details", {"uid": str(uid)})
        if not result.ok:
            raise RuntimeError(result.error or "map_place_details failed")

        detail = parse_place_details(result.data)
        claims = detail_claims(detail)
        if not claims:
            text = text_from_mcp_payload(result.data)
            claims = [Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=text[:600], confidence=0.55)]

        return [
            self._evidence(
                claims=claims,
                kwargs=kwargs,
                city=detail.get("city") or kwargs.get("city"),
                place_name=detail.get("name") or kwargs.get("place_name"),
                confidence=0.68,
                limitations=_DETAIL_LIMITATIONS,
            )
        ]

    async def _run_weather(self, kwargs: dict[str, Any]) -> list[Evidence]:
        args: dict[str, Any] = {}
        if kwargs.get("latitude") is not None and kwargs.get("longitude") is not None:
            args["location"] = f"{kwargs['latitude']},{kwargs['longitude']}"
        elif kwargs.get("district_id"):
            args["district_id"] = kwargs["district_id"]
        else:
            location = kwargs.get("city") or kwargs.get("place_name") or kwargs.get("query")
            if not location:
                raise ValueError("baidu_weather_mcp requires city, coordinates, or district_id")
            args["location"] = str(location)

        result = await self._client.invoke("baidu_map", "map_weather", args)
        if not result.ok:
            raise RuntimeError(result.error or "map_weather failed")

        weather = parse_weather(result.data)
        return [
            self._evidence(
                claims=weather_claims(weather),
                kwargs=kwargs,
                source_type=SourceType.WEATHER_API,
                confidence=0.78,
                limitations=_WEATHER_LIMITATIONS,
            )
        ]

    def _evidence(
        self,
        *,
        claims: list[Claim],
        kwargs: dict[str, Any],
        limitations: list[str],
        city: str | None = None,
        place_name: str | None = None,
        confidence: float = 0.7,
        source_type: SourceType = SourceType.MAP,
    ) -> Evidence:
        return Evidence(
            source_name="Baidu Maps MCP",
            source_type=source_type,
            source_url="https://lbsyun.baidu.com/",
            country=kwargs.get("country") or "China",
            city=city or kwargs.get("city"),
            place_name=place_name or kwargs.get("place_name"),
            retrieved_at=datetime.utcnow(),
            data_freshness=DataFreshness.LIVE if source_type == SourceType.WEATHER_API else DataFreshness.RECENT,
            license_scope=LicenseScope.API_ALLOWED,
            confidence=confidence,
            claims=claims,
            limitations=limitations,
        )
