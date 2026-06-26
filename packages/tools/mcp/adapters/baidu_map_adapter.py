from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mcp.adapters.baidu_response_parser import (
    build_map_search_places_args,
    detail_claims,
    directions_claims,
    directions_matrix_claims,
    geocode_claims,
    ip_location_claims,
    parse_directions,
    parse_directions_matrix,
    parse_geocode,
    parse_ip_location,
    parse_place_details,
    parse_reverse_geocode,
    parse_road_traffic,
    parse_search_places,
    parse_weather,
    pick_baidu_uid_from_evidence,
    reverse_geocode_claims,
    search_claims,
    traffic_claims,
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
_GEOCODE_LIMITATIONS = [
    "地理编码结果用于坐标补全和地点消歧，不等同于官方景区公告。",
]
_ROUTE_LIMITATIONS = [
    "路线规划为地图引擎估算，实际路况、封路、景区管制需以现场与官方信息为准。",
]
_TRAFFIC_LIMITATIONS = [
    "路况为实时或近实时估算，不能替代官方交通管制公告。",
]
_IP_LIMITATIONS = [
    "IP 定位仅为粗略城市/坐标估计，精度有限且涉及隐私；仅应在用户授权或明确「我附近」场景使用。",
]


class BaiduMapMCPAdapter(BaseTravelTool):
    """Baidu Map MCP — place search/detail/weather/geocode/route/traffic/ip."""

    def __init__(self, policy_name: str, client: MCPClientManager | None = None) -> None:
        self.policy_name = policy_name
        self.name = policy_name
        self.server_name = "baidu_map"
        self._client = client or get_mcp_client_manager()
        self._handlers = {
            "baidu_place_search_mcp": self._run_search,
            "baidu_place_detail_mcp": self._run_detail,
            "baidu_weather_mcp": self._run_weather,
            "baidu_geocode_mcp": self._run_geocode,
            "baidu_reverse_geocode_mcp": self._run_reverse_geocode,
            "baidu_route_mcp": self._run_route,
            "baidu_route_matrix_mcp": self._run_route_matrix,
            "baidu_traffic_mcp": self._run_traffic,
            "baidu_ip_location_mcp": self._run_ip_location,
        }

    def is_available(self) -> bool:
        return self._client.is_server_configured("baidu_map")

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason("baidu_map"))

        handler = self._handlers.get(self.policy_name)
        if handler is None:
            raise ValueError(f"Unknown Baidu policy {self.policy_name!r}")
        return await handler(kwargs)

    async def _run_search(self, kwargs: dict[str, Any]) -> list[Evidence]:
        args = build_map_search_places_args(kwargs)

        result = await self._client.invoke("baidu_map", "map_search_places", args)
        if not result.ok:
            raise RuntimeError(result.error or "map_search_places failed")

        query = args["query"]
        candidates = parse_search_places(result.data)
        if not candidates and kwargs.get("city"):
            geo = await self._client.invoke(
                "baidu_map",
                "map_geocode",
                {"address": f"{query}, {kwargs.get('city')}, {kwargs.get('country') or 'China'}"},
            )
            if geo.ok:
                parsed = parse_geocode(geo.data)
                if parsed.get("latitude") is not None and parsed.get("longitude") is not None:
                    candidates = [
                        {
                            "name": str(kwargs.get("place_name") or query),
                            "address": parsed.get("address"),
                            "city": kwargs.get("city"),
                            "latitude": parsed["latitude"],
                            "longitude": parsed["longitude"],
                        }
                    ]
                else:
                    candidates = parse_search_places(geo.data) or [
                        {"name": query, "address": text_from_mcp_payload(geo.data)[:200]}
                    ]

        if not candidates:
            text = text_from_mcp_payload(result.data)
            if text.strip():
                candidates = parse_search_places(text)
            if not candidates and text.strip():
                return [
                    self._evidence(
                        claims=[Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=text[:600], confidence=0.55)],
                        kwargs=kwargs,
                        limitations=_SEARCH_LIMITATIONS + ["Structured POI parse failed; raw text only."],
                    )
                ]
            raise RuntimeError("map_search_places returned no candidates")

        claims = search_claims(
            candidates,
            information_need=str(kwargs.get("information_need") or kwargs.get("claim_target") or ""),
            claim_target=str(kwargs.get("claim_target") or ""),
            nearby_search=bool(kwargs.get("nearby_search")),
            tag=kwargs.get("tag"),
            latitude=kwargs.get("latitude"),
            anchor_location_key=str(kwargs.get("anchor_location_key") or ""),
            anchor_candidate_name=str(kwargs.get("anchor_candidate_name") or kwargs.get("nearby_anchor_label") or ""),
        )
        city = candidates[0].get("city") or kwargs.get("city")
        anchor_label = kwargs.get("anchor_candidate_name") or kwargs.get("nearby_anchor_label")
        place_name = anchor_label or candidates[0].get("name") or kwargs.get("place_name")
        return [
            self._evidence(
                claims=claims,
                kwargs=kwargs,
                city=city,
                place_name=place_name,
                confidence=0.72 if len(candidates) == 1 else 0.62,
                limitations=_SEARCH_LIMITATIONS,
            )
        ]

    async def _run_detail(self, kwargs: dict[str, Any]) -> list[Evidence]:
        uid = await self._resolve_detail_uid(kwargs)
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

    async def _resolve_detail_uid(self, kwargs: dict[str, Any]) -> str | None:
        uid = kwargs.get("uid") or kwargs.get("poi_uid")
        if uid:
            return str(uid)

        region = kwargs.get("region") or kwargs.get("province")
        city = kwargs.get("city")
        prior = kwargs.get("prior_evidence") or kwargs.get("evidence") or []
        if isinstance(prior, list):
            uid = pick_baidu_uid_from_evidence(prior, region=region, city=city)
            if uid:
                return uid

        place = kwargs.get("place_name") or kwargs.get("query")
        search_region = city or region
        if place and search_region:
            uid = await self._search_uid_for_place(str(place), str(search_region))
            if uid:
                return uid

        lat = kwargs.get("latitude")
        lng = kwargs.get("longitude")
        if (lat is None or lng is None) and isinstance(prior, list):
            from tools.mcp.adapters.baidu_response_parser import resolve_coordinates_from_evidence

            coords = resolve_coordinates_from_evidence(prior)
            if coords:
                lat = coords["latitude"]
                lng = coords["longitude"]
        if lat is not None and lng is not None and place:
            rev = await self._client.invoke(
                "baidu_map",
                "map_reverse_geocode",
                {"location": f"{lat},{lng}"},
            )
            if rev.ok:
                parsed = parse_reverse_geocode(rev.data)
                inferred_city = parsed.get("city") or parsed.get("province")
                if inferred_city:
                    uid = await self._search_uid_for_place(str(place), str(inferred_city))
                    if uid:
                        return uid
        return None

    async def _search_uid_for_place(self, place: str, region: str) -> str | None:
        result = await self._client.invoke(
            "baidu_map",
            "map_search_places",
            {"query": place, "region": region},
        )
        if not result.ok:
            return None
        for candidate in parse_search_places(result.data):
            if candidate.get("uid"):
                return str(candidate["uid"])
        return None

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

    async def _run_geocode(self, kwargs: dict[str, Any]) -> list[Evidence]:
        address = kwargs.get("address") or kwargs.get("query") or kwargs.get("place_name")
        if not address:
            raise ValueError("baidu_geocode_mcp requires address, query, or place_name")
        region = kwargs.get("region") or kwargs.get("city") or kwargs.get("province")
        args: dict[str, Any] = {"address": str(address)}
        if region:
            args["region"] = str(region)

        result = await self._client.invoke("baidu_map", "map_geocode", args)
        if not result.ok:
            raise RuntimeError(result.error or "map_geocode failed")

        parsed = parse_geocode(result.data)
        claims = geocode_claims(parsed)
        if not claims:
            raise RuntimeError("map_geocode returned no usable coordinates")

        return [
            self._evidence(
                claims=claims,
                kwargs=kwargs,
                city=parsed.get("city") or kwargs.get("city"),
                place_name=kwargs.get("place_name"),
                confidence=0.7,
                limitations=_GEOCODE_LIMITATIONS,
            )
        ]

    async def _run_reverse_geocode(self, kwargs: dict[str, Any]) -> list[Evidence]:
        lat = kwargs.get("latitude") or kwargs.get("lat")
        lng = kwargs.get("longitude") or kwargs.get("lng") or kwargs.get("lon")
        if lat is None or lng is None:
            raise ValueError("baidu_reverse_geocode_mcp requires latitude and longitude")

        result = await self._client.invoke(
            "baidu_map",
            "map_reverse_geocode",
            {"location": f"{lat},{lng}"},
        )
        if not result.ok:
            raise RuntimeError(result.error or "map_reverse_geocode failed")

        parsed = parse_reverse_geocode(result.data)
        claims = reverse_geocode_claims(parsed)
        if not claims:
            text = text_from_mcp_payload(result.data)
            claims = [Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=text[:600], confidence=0.55)]

        return [
            self._evidence(
                claims=claims,
                kwargs=kwargs,
                city=parsed.get("city") or kwargs.get("city"),
                confidence=0.68,
                limitations=_GEOCODE_LIMITATIONS,
            )
        ]

    async def _run_route(self, kwargs: dict[str, Any]) -> list[Evidence]:
        origin = kwargs.get("origin") or kwargs.get("from")
        destination = kwargs.get("destination") or kwargs.get("to") or kwargs.get("place_name")
        if not origin or not destination:
            raise ValueError("baidu_route_mcp requires origin and destination")

        args: dict[str, Any] = {
            "origin": str(origin),
            "destination": str(destination),
            "mode": kwargs.get("mode") or kwargs.get("transport_mode") or "driving",
        }
        result = await self._client.invoke("baidu_map", "map_directions", args)
        if not result.ok:
            raise RuntimeError(result.error or "map_directions failed")

        parsed = parse_directions(result.data)
        claims = directions_claims(parsed)
        if not claims:
            text = text_from_mcp_payload(result.data)
            claims = [Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=text[:600], confidence=0.55)]

        return [
            self._evidence(
                claims=claims,
                kwargs=kwargs,
                confidence=0.72,
                limitations=_ROUTE_LIMITATIONS,
            )
        ]

    async def _run_route_matrix(self, kwargs: dict[str, Any]) -> list[Evidence]:
        origins = kwargs.get("origins") or kwargs.get("origin")
        destinations = kwargs.get("destinations") or kwargs.get("destination")
        if not origins or not destinations:
            raise ValueError("baidu_route_matrix_mcp requires origins and destinations")

        args: dict[str, Any] = {
            "origins": origins,
            "destinations": destinations,
            "mode": kwargs.get("mode") or "driving",
        }
        result = await self._client.invoke("baidu_map", "map_directions_matrix", args)
        if not result.ok:
            raise RuntimeError(result.error or "map_directions_matrix failed")

        parsed = parse_directions_matrix(result.data)
        claims = directions_matrix_claims(parsed)
        if not claims:
            text = text_from_mcp_payload(result.data)
            claims = [Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=text[:600], confidence=0.55)]

        return [
            self._evidence(
                claims=claims,
                kwargs=kwargs,
                confidence=0.7,
                limitations=_ROUTE_LIMITATIONS,
            )
        ]

    async def _run_traffic(self, kwargs: dict[str, Any]) -> list[Evidence]:
        road = kwargs.get("road_name") or kwargs.get("road") or kwargs.get("query")
        if not road:
            raise ValueError("baidu_traffic_mcp requires road_name or query")

        args: dict[str, Any] = {"road_name": str(road)}
        if kwargs.get("city"):
            args["city"] = str(kwargs["city"])

        result = await self._client.invoke("baidu_map", "map_road_traffic", args)
        if not result.ok:
            raise RuntimeError(result.error or "map_road_traffic failed")

        parsed = parse_road_traffic(result.data)
        claims = traffic_claims(parsed)
        if not claims:
            text = text_from_mcp_payload(result.data)
            claims = [Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=text[:600], confidence=0.55)]

        return [
            self._evidence(
                claims=claims,
                kwargs=kwargs,
                confidence=0.72,
                limitations=_TRAFFIC_LIMITATIONS,
            )
        ]

    async def _run_ip_location(self, kwargs: dict[str, Any]) -> list[Evidence]:
        args: dict[str, Any] = {}
        if kwargs.get("ip"):
            args["ip"] = str(kwargs["ip"])

        result = await self._client.invoke("baidu_map", "map_ip_location", args)
        if not result.ok:
            raise RuntimeError(result.error or "map_ip_location failed")

        parsed = parse_ip_location(result.data)
        claims = ip_location_claims(parsed)
        if not claims:
            raise RuntimeError("map_ip_location returned no location estimate")

        return [
            self._evidence(
                claims=claims,
                kwargs=kwargs,
                city=parsed.get("city"),
                confidence=0.55,
                limitations=_IP_LIMITATIONS,
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
