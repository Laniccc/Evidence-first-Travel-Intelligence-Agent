from __future__ import annotations

import json
import re
from typing import Any

from app.schemas.evidence import Claim, ClaimType

_POI_NAME_RE = re.compile(r'"name"\s*:\s*"((?:\\.|[^"\\])*)"')
_POI_UID_RE = re.compile(r'"uid"\s*:\s*"([^"]+)"')
_POI_LAT_RE = re.compile(r'"(?:lat|latitude)"\s*:\s*([-\d.]+)')
_POI_LNG_RE = re.compile(r'"(?:lng|lon|longitude)"\s*:\s*([-\d.]+)')
_POI_CITY_RE = re.compile(r'"city"\s*:\s*"((?:\\.|[^"\\])*)"')
_POI_PROVINCE_RE = re.compile(r'"province"\s*:\s*"((?:\\.|[^"\\])*)"')
_POI_ADDRESS_RE = re.compile(r'"address"\s*:\s*"((?:\\.|[^"\\])*)"')


def coerce_baidu_payload(data: Any) -> Any:
    """Unwrap MCP wrappers (truncated preview, text, content blocks) before parsing."""
    if isinstance(data, str):
        stripped = data.strip()
        if not stripped:
            return data
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return coerce_baidu_payload(json.loads(stripped))
            except json.JSONDecodeError:
                return stripped
        return stripped
    if isinstance(data, list):
        if data and all(isinstance(x, dict) for x in data):
            if any(k in data[0] for k in ("name", "uid", "title", "place_name")):
                return data
        texts: list[str] = []
        for block in data:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                texts.append(block["text"])
        if texts:
            return coerce_baidu_payload("\n".join(texts))
        return data
    if not isinstance(data, dict):
        return data
    if data.get("truncated") and isinstance(data.get("preview"), str):
        return coerce_baidu_payload(data["preview"])
    for key in ("text", "body", "markdown"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return coerce_baidu_payload(val)
    content = data.get("content")
    if isinstance(content, str) and content.strip():
        return coerce_baidu_payload(content)
    if isinstance(content, list):
        return coerce_baidu_payload(content)
    if isinstance(data.get("data"), (dict, list, str)):
        inner = data["data"]
        if inner is not data:
            return coerce_baidu_payload(inner)
    result = data.get("result")
    if isinstance(result, dict) and any(k in result for k in ("results", "places", "pois")):
        return result
    return data


def _as_list(data: Any, *keys: str) -> list[dict[str, Any]]:
    data = coerce_baidu_payload(data)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in keys:
            bucket = data.get(key)
            if isinstance(bucket, list):
                return [x for x in bucket if isinstance(x, dict)]
        if isinstance(data.get("text"), str):
            try:
                parsed = json.loads(data["text"])
                return _as_list(parsed, *keys)
            except json.JSONDecodeError:
                return []
    if isinstance(data, str):
        return _extract_pois_from_json_blob(data)
    return []


def _item_coordinates(item: dict[str, Any]) -> tuple[Any, Any]:
    lat = item.get("lat") or item.get("latitude")
    lon = item.get("lng") or item.get("lon") or item.get("longitude")
    location = item.get("location")
    if isinstance(location, dict):
        lat = lat or location.get("lat") or location.get("latitude")
        lon = lon or location.get("lng") or location.get("lon") or location.get("longitude")
    detail = item.get("detail_info")
    if isinstance(detail, dict):
        navi = detail.get("navi_location")
        if isinstance(navi, dict):
            lat = lat or navi.get("lat") or navi.get("latitude")
            lon = lon or navi.get("lng") or navi.get("lon") or navi.get("longitude")
    return lat, lon


def _extract_pois_from_json_blob(text: str) -> list[dict[str, Any]]:
    """Best-effort POI extraction when MCP payload JSON is truncated or unparseable."""
    if not text or "results" not in text:
        return []
    names = _POI_NAME_RE.findall(text)
    if not names:
        return []
    uids = _POI_UID_RE.findall(text)
    lats = _POI_LAT_RE.findall(text)
    lngs = _POI_LNG_RE.findall(text)
    cities = _POI_CITY_RE.findall(text)
    provinces = _POI_PROVINCE_RE.findall(text)
    addresses = _POI_ADDRESS_RE.findall(text)
    candidates: list[dict[str, Any]] = []
    for idx, raw_name in enumerate(names[:8]):
        name = raw_name.encode("utf-8").decode("unicode_escape") if "\\u" in raw_name else raw_name
        lat = float(lats[idx]) if idx < len(lats) else (float(lats[0]) if lats else None)
        lon = float(lngs[idx]) if idx < len(lngs) else (float(lngs[0]) if lngs else None)
        candidates.append(
            {
                "name": name,
                "uid": uids[idx] if idx < len(uids) else (uids[0] if uids else None),
                "city": cities[idx] if idx < len(cities) else (cities[0] if cities else None),
                "province": provinces[idx] if idx < len(provinces) else (provinces[0] if provinces else None),
                "address": addresses[idx] if idx < len(addresses) else (addresses[0] if addresses else None),
                "latitude": lat,
                "longitude": lon,
            }
        )
    return candidates


def parse_search_places(data: Any) -> list[dict[str, Any]]:
    items = _as_list(data, "results", "places", "pois", "data")
    if not items and isinstance(coerce_baidu_payload(data), str):
        items = _extract_pois_from_json_blob(str(coerce_baidu_payload(data)))
    candidates: list[dict[str, Any]] = []
    for item in items:
        name = item.get("name") or item.get("title") or item.get("place_name") or ""
        uid = item.get("uid") or item.get("id") or item.get("poi_uid")
        city = item.get("city") or item.get("cityname")
        province = item.get("province") or item.get("provincename")
        address = item.get("address") or item.get("addr")
        lat, lon = _item_coordinates(item)
        if not name and not uid:
            continue
        try:
            lat_f = float(lat) if lat is not None else None
        except (TypeError, ValueError):
            lat_f = None
        try:
            lon_f = float(lon) if lon is not None else None
        except (TypeError, ValueError):
            lon_f = None
        candidates.append(
            {
                "name": str(name),
                "uid": str(uid) if uid else None,
                "city": str(city) if city else None,
                "province": str(province) if province else None,
                "address": str(address) if address else None,
                "latitude": lat_f,
                "longitude": lon_f,
                "tag": str(item.get("tag") or item.get("type") or item.get("std_tag") or "")
                or None,
            }
        )
    return candidates


def parse_place_details(data: Any) -> dict[str, Any]:
    data = coerce_baidu_payload(data)
    if not isinstance(data, dict):
        return {"raw": str(data)[:2000]}
    detail = data.get("result") if isinstance(data.get("result"), dict) else data
    lat, lon = _item_coordinates(detail)
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
        "latitude": lat,
        "longitude": lon,
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


def _location_key(candidate: dict[str, Any]) -> str:
    province = (candidate.get("province") or "").strip()
    city = (candidate.get("city") or "").strip()
    name = (candidate.get("name") or "").strip()
    return f"{province}|{city}|{name}"


def candidates_are_ambiguous(candidates: list[dict[str, Any]]) -> bool:
    if len(candidates) < 2:
        return False
    return len({_location_key(c) for c in candidates}) > 1


def build_map_search_places_args(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Build map_search_places invoke args; region/bounds/location are mutually exclusive."""
    query = kwargs.get("query") or kwargs.get("place_name") or ""
    if not query:
        raise ValueError("baidu_place_search_mcp requires query or place_name")

    args: dict[str, Any] = {"query": str(query)}
    tag = kwargs.get("tag")
    if tag:
        args["tag"] = str(tag)

    bounds = kwargs.get("bounds")
    lat = kwargs.get("latitude")
    lng = kwargs.get("longitude")
    location = kwargs.get("location")
    radius = kwargs.get("radius")
    region = kwargs.get("region") or kwargs.get("city") or kwargs.get("province")

    if bounds:
        args["bounds"] = str(bounds)
    elif location or (lat is not None and lng is not None):
        args["location"] = location or f"{lat},{lng}"
        if radius is not None:
            args["radius"] = int(radius)
        elif kwargs.get("nearby_search"):
            args["radius"] = 3000
    elif region:
        args["region"] = str(region)

    return args


def search_claims(
    candidates: list[dict[str, Any]],
    *,
    information_need: str | None = None,
    claim_target: str | None = None,
    nearby_search: bool = False,
    tag: str | None = None,
    latitude: Any = None,
    anchor_location_key: str = "",
    anchor_candidate_name: str = "",
) -> list[Claim]:
    from tools.mcp.adapters.nearby_poi_claims import (
        append_nearby_recommendation_claims,
        is_nearby_retrieval,
    )

    nearby_mode = is_nearby_retrieval(
        information_need=information_need,
        claim_target=claim_target,
        nearby_search=nearby_search,
        tag=tag,
        latitude=latitude,
    )
    claims: list[Claim] = []
    ambiguous = candidates_are_ambiguous(candidates)
    if candidates:
        claims.append(
            Claim(
                claim_type=ClaimType.PLACE_CANDIDATES,
                value=candidates,
                normalized_value={"candidates": candidates},
                confidence=0.7 if len(candidates) == 1 else 0.6,
            )
        )
    if nearby_mode:
        need = information_need or claim_target or "nearby_poi"
        return append_nearby_recommendation_claims(
            claims,
            candidates,
            str(need),
            anchor_location_key=anchor_location_key,
            anchor_candidate_name=anchor_candidate_name,
            search_tag=tag,
        )
    if ambiguous:
        return claims
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
                normalized_value={
                    "rating": detail["rating"],
                    "uid": detail.get("uid"),
                    "name": detail.get("name"),
                },
                confidence=0.6,
            )
        )
    lat = detail.get("latitude")
    lon = detail.get("longitude")
    if lat is not None and lon is not None:
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            lat_f = lon_f = None
        if lat_f is not None and lon_f is not None:
            claims.append(
                Claim(
                    claim_type=ClaimType.COORDINATES,
                    value={"latitude": lat_f, "longitude": lon_f},
                    normalized_value={"latitude": lat_f, "longitude": lon_f},
                    confidence=0.72,
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


def _candidate_matches_region(candidate: dict[str, Any], *, region: str | None, city: str | None) -> bool:
    if not region and not city:
        return True
    cand_city = (candidate.get("city") or "").strip()
    cand_province = (candidate.get("province") or "").strip()
    if city and city in (cand_city, cand_province):
        return True
    if region and region in (cand_city, cand_province):
        return True
    return False


def pick_baidu_uid_from_evidence(
    evidence_list: list,
    *,
    region: str | None = None,
    city: str | None = None,
) -> str | None:
    for ev in evidence_list:
        for claim in getattr(ev, "claims", []) or []:
            if claim.claim_type == ClaimType.POI_UID:
                uid = _uid_from_claim_value(claim.value)
                if uid and not uid.startswith("{"):
                    return uid
            nv = claim.normalized_value
            if isinstance(nv, dict) and nv.get("uid"):
                return str(nv["uid"])
            if claim.claim_type == ClaimType.TRAVEL_ADVICE:
                uid = _uid_from_claim_value(claim.value)
                if uid:
                    return uid
        candidates_claim = next(
            (c for c in getattr(ev, "claims", []) if c.claim_type == ClaimType.PLACE_CANDIDATES),
            None,
        )
        if candidates_claim and isinstance(candidates_claim.normalized_value, dict):
            bucket = candidates_claim.normalized_value.get("candidates") or candidates_claim.value
            if isinstance(bucket, list):
                for item in bucket:
                    if not isinstance(item, dict):
                        continue
                    if not _candidate_matches_region(item, region=region, city=city):
                        continue
                    uid = item.get("uid")
                    if uid:
                        return str(uid)
                if not (region or city) and bucket and isinstance(bucket[0], dict):
                    uid = bucket[0].get("uid")
                    if uid:
                        return str(uid)
    return None


def _unwrap_result(data: Any) -> dict[str, Any]:
    data = coerce_baidu_payload(data)
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


def _coords_from_claim_value(val: Any) -> dict[str, float] | None:
    if isinstance(val, dict):
        lat = val.get("latitude") if val.get("latitude") is not None else val.get("lat")
        lng = val.get("longitude") if val.get("longitude") is not None else val.get("lng")
        if lat is not None and lng is not None:
            try:
                return {"latitude": float(lat), "longitude": float(lng)}
            except (TypeError, ValueError):
                return None
    if isinstance(val, str) and "results" in val:
        for item in _extract_pois_from_json_blob(val):
            if item.get("latitude") is not None and item.get("longitude") is not None:
                return {"latitude": float(item["latitude"]), "longitude": float(item["longitude"])}
        lats = _POI_LAT_RE.findall(val)
        lngs = _POI_LNG_RE.findall(val)
        if lats and lngs:
            try:
                return {"latitude": float(lats[0]), "longitude": float(lngs[0])}
            except (TypeError, ValueError):
                return None
    return None


def _uid_from_claim_value(val: Any) -> str | None:
    if isinstance(val, str) and val.strip():
        if val.startswith("{") and "uid" in val:
            matches = _POI_UID_RE.findall(val)
            return matches[0] if matches else None
        return val.strip()
    return None


_NEARBY_QUALIFIER_PATTERNS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"北门|玄武门|和平门"), ("和平门", "玄武门", "北门")),
    (re.compile(r"解放门"), ("解放门",)),
    (re.compile(r"情侣园门|情侣园"), ("情侣园",)),
    (re.compile(r"太平门"), ("太平门",)),
    (re.compile(r"南门|正大门|主入口"), ("正门", "南门", "主入口")),
    (re.compile(r"东门"), ("东门",)),
    (re.compile(r"西门"), ("西门",)),
]


def gate_tokens_from_user_query(user_query: str) -> tuple[str, ...]:
    return _gate_tokens_from_user_query(user_query)


def _gate_tokens_from_user_query(user_query: str) -> tuple[str, ...]:
    text = (user_query or "").strip()
    if not text:
        return ()
    tokens: list[str] = []
    for pattern, names in _NEARBY_QUALIFIER_PATTERNS:
        if pattern.search(text):
            tokens.extend(names)
    return tuple(dict.fromkeys(tokens))


def _coords_from_place_candidate(item: dict) -> dict[str, float] | None:
    if not isinstance(item, dict):
        return None
    lat, lng = item.get("latitude"), item.get("longitude")
    if lat is None or lng is None:
        return None
    return {"latitude": float(lat), "longitude": float(lng)}


def _iter_place_candidate_items(claim) -> list[dict]:
    bucket = claim.normalized_value or claim.value
    if isinstance(bucket, dict):
        bucket = bucket.get("candidates") or []
    if isinstance(bucket, list):
        return [item for item in bucket if isinstance(item, dict)]
    return []


def resolve_nearby_anchor_coordinates(
    evidence_list: list,
    *,
    user_query: str = "",
    structured_result: dict | None = None,
) -> dict[str, float] | None:
    """Pick gate/entrance coords when the user names 北门/解放门/etc.; else first anchor."""
    gate_tokens = _gate_tokens_from_user_query(user_query)
    if gate_tokens:
        for ev in evidence_list:
            for claim in getattr(ev, "claims", []) or []:
                if claim.claim_type != ClaimType.PLACE_CANDIDATES:
                    continue
                for item in _iter_place_candidate_items(claim):
                    label = " ".join(
                        filter(
                            None,
                            [
                                str(item.get("name") or ""),
                                str(item.get("address") or ""),
                            ],
                        )
                    )
                    if not label:
                        continue
                    if any(token in label for token in gate_tokens):
                        coords = _coords_from_place_candidate(item)
                        if coords:
                            return coords
    return resolve_coordinates_from_evidence(evidence_list, structured_result=structured_result)


def resolve_coordinates_from_evidence(
    evidence_list: list,
    *,
    structured_result: dict | None = None,
) -> dict[str, float] | None:
    for ev in evidence_list:
        for claim in getattr(ev, "claims", []) or []:
            if claim.claim_type == ClaimType.COORDINATES:
                coords = _coords_from_claim_value(claim.normalized_value) or _coords_from_claim_value(claim.value)
                if coords:
                    return coords
            if claim.claim_type == ClaimType.PLACE_CANDIDATES:
                for item in _iter_place_candidate_items(claim):
                    coords = _coords_from_place_candidate(item)
                    if coords:
                        return coords
            if claim.claim_type == ClaimType.TRAVEL_ADVICE:
                coords = _coords_from_claim_value(claim.value)
                if coords:
                    return coords
    if isinstance(structured_result, dict):
        resolved = structured_result.get("resolved_coordinates")
        if isinstance(resolved, dict):
            coords = _coords_from_claim_value(resolved)
            if coords:
                return coords
    return None
