from __future__ import annotations

import json
from typing import Any

from app.schemas.evidence import Claim, ClaimType


def _as_list(data: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in keys:
            bucket = data.get(key)
            if isinstance(bucket, list):
                return [x for x in bucket if isinstance(x, dict)]
        if "text" in data and isinstance(data["text"], str):
            try:
                parsed = json.loads(data["text"])
                return _as_list(parsed, *keys)
            except json.JSONDecodeError:
                return []
    return []


def parse_search_places(data: Any) -> list[dict[str, Any]]:
    items = _as_list(data, "results", "places", "pois", "data")
    candidates: list[dict[str, Any]] = []
    for item in items:
        name = item.get("name") or item.get("title") or item.get("place_name") or ""
        uid = item.get("uid") or item.get("id") or item.get("poi_uid")
        city = item.get("city") or item.get("cityname")
        province = item.get("province") or item.get("provincename")
        address = item.get("address") or item.get("addr")
        lat = item.get("lat") or item.get("latitude")
        lon = item.get("lng") or item.get("lon") or item.get("longitude")
        if not name and not uid:
            continue
        candidates.append(
            {
                "name": str(name),
                "uid": str(uid) if uid else None,
                "city": str(city) if city else None,
                "province": str(province) if province else None,
                "address": str(address) if address else None,
                "latitude": float(lat) if lat is not None else None,
                "longitude": float(lon) if lon is not None else None,
            }
        )
    return candidates


def parse_place_details(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and "text" in data and len(data) == 1:
        try:
            data = json.loads(data["text"])
        except json.JSONDecodeError:
            pass
    if not isinstance(data, dict):
        return {"raw": str(data)[:2000]}
    detail = data.get("result") if isinstance(data.get("result"), dict) else data
    return {
        "uid": detail.get("uid") or detail.get("id"),
        "name": detail.get("name") or detail.get("title"),
        "address": detail.get("address") or detail.get("addr"),
        "city": detail.get("city") or detail.get("cityname"),
        "province": detail.get("province") or detail.get("provincename"),
        "opening_hours": detail.get("shop_hours") or detail.get("opening_hours") or detail.get("opentime"),
        "price": detail.get("price") or detail.get("ticket_price") or detail.get("cost"),
        "rating": detail.get("overall_rating") or detail.get("rating"),
        "phone": detail.get("telephone") or detail.get("phone"),
        "latitude": detail.get("lat") or detail.get("latitude"),
        "longitude": detail.get("lng") or detail.get("lon") or detail.get("longitude"),
    }


def parse_weather(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and "text" in data and len(data) == 1:
        try:
            data = json.loads(data["text"])
        except json.JSONDecodeError:
            pass
    if not isinstance(data, dict):
        return {"summary": str(data)[:1200]}
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    return {
        "current": result.get("now") or result.get("current"),
        "forecast": result.get("forecasts") or result.get("forecast") or result.get("daily"),
        "summary": json.dumps(result, ensure_ascii=False)[:1200],
    }


def search_claims(candidates: list[dict[str, Any]]) -> list[Claim]:
    claims: list[Claim] = []
    if candidates:
        claims.append(
            Claim(
                claim_type=ClaimType.PLACE_CANDIDATES,
                value=candidates,
                normalized_value={"candidates": candidates},
                confidence=0.7 if len(candidates) == 1 else 0.6,
            )
        )
    top = candidates[0] if candidates else {}
    if top.get("uid"):
        claims.append(
            Claim(
                claim_type=ClaimType.POI_UID,
                value=top["uid"],
                normalized_value={"uid": top["uid"]},
                confidence=0.72,
            )
        )
    if top.get("address"):
        claims.append(
            Claim(
                claim_type=ClaimType.ADDRESS,
                value=top["address"],
                confidence=0.68,
            )
        )
    if top.get("latitude") is not None and top.get("longitude") is not None:
        claims.append(
            Claim(
                claim_type=ClaimType.COORDINATES,
                value={"latitude": top["latitude"], "longitude": top["longitude"]},
                normalized_value={"latitude": top["latitude"], "longitude": top["longitude"]},
                confidence=0.75,
            )
        )
    return claims


def detail_claims(detail: dict[str, Any]) -> list[Claim]:
    claims: list[Claim] = []
    if detail.get("uid"):
        claims.append(
            Claim(
                claim_type=ClaimType.POI_UID,
                value=detail["uid"],
                normalized_value={"uid": detail["uid"]},
                confidence=0.72,
            )
        )
    if detail.get("address"):
        claims.append(
            Claim(claim_type=ClaimType.ADDRESS, value=str(detail["address"]), confidence=0.7)
        )
    if detail.get("opening_hours"):
        claims.append(
            Claim(
                claim_type=ClaimType.OPENING_HOURS_CANDIDATE,
                value=str(detail["opening_hours"]),
                confidence=0.62,
            )
        )
    if detail.get("price"):
        claims.append(
            Claim(
                claim_type=ClaimType.PRICE_CANDIDATE,
                value=str(detail["price"]),
                confidence=0.58,
            )
        )
    if detail.get("rating"):
        claims.append(
            Claim(
                claim_type=ClaimType.RATING_CANDIDATE,
                value=str(detail["rating"]),
                confidence=0.6,
            )
        )
    return claims


def weather_claims(weather: dict[str, Any]) -> list[Claim]:
    summary = weather.get("summary") or json.dumps(weather, ensure_ascii=False)[:800]
    return [
        Claim(
            claim_type=ClaimType.WEATHER,
            value=summary,
            raw_text=summary,
            confidence=0.75,
        )
    ]


def pick_baidu_uid_from_evidence(evidence_list: list) -> str | None:
    for ev in evidence_list:
        for claim in getattr(ev, "claims", []) or []:
            if claim.claim_type == ClaimType.POI_UID:
                return str(claim.value)
            nv = claim.normalized_value
            if isinstance(nv, dict) and nv.get("uid"):
                return str(nv["uid"])
        candidates_claim = next(
            (c for c in getattr(ev, "claims", []) if c.claim_type == ClaimType.PLACE_CANDIDATES),
            None,
        )
        if candidates_claim and isinstance(candidates_claim.normalized_value, dict):
            bucket = candidates_claim.normalized_value.get("candidates") or candidates_claim.value
            if isinstance(bucket, list) and bucket and isinstance(bucket[0], dict):
                uid = bucket[0].get("uid")
                if uid:
                    return str(uid)
    return None


def _unwrap_result(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and "text" in data and len(data) == 1:
        try:
            data = json.loads(data["text"])
        except json.JSONDecodeError:
            pass
    if not isinstance(data, dict):
        return {"raw": str(data)[:2000]}
    result = data.get("result")
    if isinstance(result, dict):
        return result
    return data


def parse_geocode(data: Any) -> dict[str, Any]:
    result = _unwrap_result(data)
    location = result.get("location") or result
    lat = location.get("lat") or location.get("latitude") or result.get("lat")
    lng = location.get("lng") or location.get("lon") or location.get("longitude") or result.get("lng")
    return {
        "latitude": float(lat) if lat is not None else None,
        "longitude": float(lng) if lng is not None else None,
        "address": result.get("formatted_address") or result.get("address") or result.get("name"),
        "city": result.get("city") or result.get("cityname"),
        "province": result.get("province") or result.get("provincename"),
        "confidence": result.get("confidence"),
    }


def parse_reverse_geocode(data: Any) -> dict[str, Any]:
    result = _unwrap_result(data)
    address = result.get("formatted_address") or result.get("address")
    return {
        "address": address,
        "city": result.get("addressComponent", {}).get("city")
        if isinstance(result.get("addressComponent"), dict)
        else result.get("city") or result.get("cityname"),
        "province": result.get("addressComponent", {}).get("province")
        if isinstance(result.get("addressComponent"), dict)
        else result.get("province") or result.get("provincename"),
        "district": result.get("addressComponent", {}).get("district")
        if isinstance(result.get("addressComponent"), dict)
        else result.get("district"),
        "latitude": result.get("location", {}).get("lat")
        if isinstance(result.get("location"), dict)
        else result.get("lat"),
        "longitude": result.get("location", {}).get("lng")
        if isinstance(result.get("location"), dict)
        else result.get("lng"),
    }


def parse_directions(data: Any) -> dict[str, Any]:
    result = _unwrap_result(data)
    routes = result.get("routes") or result.get("route") or []
    if isinstance(routes, dict):
        routes = [routes]
    route = routes[0] if routes else result
    distance = route.get("distance") or result.get("distance")
    duration = route.get("duration") or result.get("duration")
    steps = route.get("steps") or result.get("steps") or []
    return {
        "distance_m": distance,
        "duration_s": duration,
        "steps": steps[:20] if isinstance(steps, list) else [],
        "summary": json.dumps(route, ensure_ascii=False)[:1200],
    }


def parse_directions_matrix(data: Any) -> dict[str, Any]:
    result = _unwrap_result(data)
    return {
        "distances": result.get("distances") or result.get("distance"),
        "durations": result.get("durations") or result.get("duration"),
        "summary": json.dumps(result, ensure_ascii=False)[:1200],
    }


def parse_road_traffic(data: Any) -> dict[str, Any]:
    result = _unwrap_result(data)
    evaluation = result.get("evaluation") or result.get("traffic_condition") or result.get("status")
    congestion = result.get("congestion") or result.get("congestion_index") or result.get("congestion_level")
    return {
        "status": evaluation or result.get("description"),
        "congestion": congestion,
        "summary": json.dumps(result, ensure_ascii=False)[:1200],
    }


def parse_ip_location(data: Any) -> dict[str, Any]:
    result = _unwrap_result(data)
    content = result.get("content") if isinstance(result.get("content"), dict) else result
    point = content.get("point") if isinstance(content.get("point"), dict) else {}
    return {
        "city": content.get("address_detail", {}).get("city")
        if isinstance(content.get("address_detail"), dict)
        else content.get("city"),
        "province": content.get("address_detail", {}).get("province")
        if isinstance(content.get("address_detail"), dict)
        else content.get("province"),
        "latitude": point.get("y") or content.get("lat"),
        "longitude": point.get("x") or content.get("lng"),
        "address": content.get("address"),
    }


def geocode_claims(parsed: dict[str, Any]) -> list[Claim]:
    claims: list[Claim] = []
    if parsed.get("latitude") is not None and parsed.get("longitude") is not None:
        claims.append(
            Claim(
                claim_type=ClaimType.COORDINATES,
                value={"latitude": parsed["latitude"], "longitude": parsed["longitude"]},
                normalized_value={"latitude": parsed["latitude"], "longitude": parsed["longitude"]},
                confidence=0.72,
            )
        )
    if parsed.get("address"):
        claims.append(
            Claim(
                claim_type=ClaimType.RESOLVED_ADDRESS,
                value=str(parsed["address"]),
                confidence=0.7,
            )
        )
    if parsed.get("city"):
        claims.append(
            Claim(
                claim_type=ClaimType.INFERRED_CITY,
                value=str(parsed["city"]),
                confidence=0.68,
            )
        )
    return claims


def reverse_geocode_claims(parsed: dict[str, Any]) -> list[Claim]:
    claims: list[Claim] = []
    if parsed.get("address"):
        claims.append(
            Claim(claim_type=ClaimType.RESOLVED_ADDRESS, value=str(parsed["address"]), confidence=0.72)
        )
    if parsed.get("city"):
        claims.append(
            Claim(claim_type=ClaimType.INFERRED_CITY, value=str(parsed["city"]), confidence=0.7)
        )
    if parsed.get("latitude") is not None and parsed.get("longitude") is not None:
        claims.append(
            Claim(
                claim_type=ClaimType.COORDINATES,
                value={"latitude": parsed["latitude"], "longitude": parsed["longitude"]},
                normalized_value={"latitude": parsed["latitude"], "longitude": parsed["longitude"]},
                confidence=0.7,
            )
        )
    return claims


def directions_claims(parsed: dict[str, Any]) -> list[Claim]:
    claims: list[Claim] = []
    if parsed.get("distance_m") is not None:
        claims.append(
            Claim(
                claim_type=ClaimType.DISTANCE,
                value=parsed["distance_m"],
                normalized_value={"meters": parsed["distance_m"]},
                confidence=0.72,
            )
        )
    if parsed.get("duration_s") is not None:
        claims.append(
            Claim(
                claim_type=ClaimType.DURATION,
                value=parsed["duration_s"],
                normalized_value={"seconds": parsed["duration_s"]},
                confidence=0.72,
            )
        )
    if parsed.get("steps"):
        claims.append(
            Claim(
                claim_type=ClaimType.ROUTE_STEPS,
                value=parsed["steps"],
                confidence=0.68,
            )
        )
    if not claims and parsed.get("summary"):
        claims.append(
            Claim(claim_type=ClaimType.TRAVEL_ADVICE, value=parsed["summary"], confidence=0.6)
        )
    return claims


def directions_matrix_claims(parsed: dict[str, Any]) -> list[Claim]:
    claims: list[Claim] = []
    if parsed.get("distances") is not None:
        claims.append(
            Claim(
                claim_type=ClaimType.DISTANCE,
                value=parsed["distances"],
                normalized_value={"matrix": parsed["distances"]},
                confidence=0.7,
            )
        )
    if parsed.get("durations") is not None:
        claims.append(
            Claim(
                claim_type=ClaimType.DURATION,
                value=parsed["durations"],
                normalized_value={"matrix": parsed["durations"]},
                confidence=0.7,
            )
        )
    return claims


def traffic_claims(parsed: dict[str, Any]) -> list[Claim]:
    claims: list[Claim] = []
    if parsed.get("status"):
        claims.append(
            Claim(
                claim_type=ClaimType.TRAFFIC_STATUS,
                value=str(parsed["status"]),
                confidence=0.72,
            )
        )
    if parsed.get("congestion") is not None:
        claims.append(
            Claim(
                claim_type=ClaimType.CONGESTION_RISK,
                value=parsed["congestion"],
                confidence=0.68,
            )
        )
    if not claims and parsed.get("summary"):
        claims.append(
            Claim(claim_type=ClaimType.TRAFFIC_STATUS, value=parsed["summary"], confidence=0.6)
        )
    return claims


def ip_location_claims(parsed: dict[str, Any]) -> list[Claim]:
    claims: list[Claim] = []
    if parsed.get("city"):
        claims.append(
            Claim(
                claim_type=ClaimType.INFERRED_CITY,
                value=str(parsed["city"]),
                confidence=0.55,
            )
        )
    loc = {
        "city": parsed.get("city"),
        "province": parsed.get("province"),
        "latitude": parsed.get("latitude"),
        "longitude": parsed.get("longitude"),
        "address": parsed.get("address"),
    }
    if any(v is not None for v in loc.values()):
        claims.append(
            Claim(
                claim_type=ClaimType.USER_LOCATION_ESTIMATION,
                value=loc,
                normalized_value=loc,
                confidence=0.55,
            )
        )
    return claims


def resolve_coordinates_from_evidence(evidence_list: list) -> dict[str, float] | None:
    for ev in evidence_list:
        for claim in getattr(ev, "claims", []) or []:
            if claim.claim_type != ClaimType.COORDINATES:
                continue
            nv = claim.normalized_value
            if isinstance(nv, dict) and nv.get("latitude") is not None and nv.get("longitude") is not None:
                return {"latitude": float(nv["latitude"]), "longitude": float(nv["longitude"])}
            val = claim.value
            if isinstance(val, dict) and val.get("latitude") is not None and val.get("longitude") is not None:
                return {"latitude": float(val["latitude"]), "longitude": float(val["longitude"])}
    return None
