"""Shared MCP argument enrichment for sub-agents and S5 CALL_TOOL."""

from __future__ import annotations

from app.config import get_settings
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.information_need_aliases import (
    is_nearby_need,
    normalize_need,
    query_text_from_state,
    resolve_nearby_need,
)
from app.orchestrator.nearby_recommendation_policy import BAIDU_TAG_BY_NEED, baidu_tag_for_need, nearby_query_suffix_for_need
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import is_mcp_policy_tool
from tools.ticketing.provider_config import is_ticket_provider_tool


def enrich_mcp_tool_arguments(
    tool_name: str,
    arguments: dict,
    *,
    state: TravelAgentState,
    prompt_context: dict | None = None,
) -> dict:
    """Merge task/state context into MCP tool payload."""
    prompt_context = prompt_context or {}
    args = dict(arguments)
    goal = state.user_goal
    frame = state.semantic_frame
    place_name = (
        args.get("place_name")
        or prompt_context.get("place_name")
        or (frame.entities.places[0] if frame and frame.entities and frame.entities.places else None)
    )
    city = (
        args.get("city")
        or prompt_context.get("city")
        or (goal.destination_city if goal else None)
        or (frame.entities.city if frame else None)
    )
    country = (
        args.get("country")
        or prompt_context.get("country")
        or (goal.destination_country if goal else None)
        or (frame.entities.country if frame else None)
    )

    if tool_name in {"official", "places", "reviews", "transit", "restaurant"} or tool_name.endswith("_mcp"):
        effective_place = place_name or city
        if effective_place and "place_name" not in args:
            args["place_name"] = effective_place
        if country and "country" not in args:
            args["country"] = country
        if city and "city" not in args:
            args["city"] = city
        if goal and goal.start_location and "start_location" not in args:
            args["start_location"] = goal.start_location

    if is_ticket_provider_tool(tool_name):
        effective_place = place_name or city
        if effective_place:
            args.setdefault("place_name", effective_place)
        if country:
            args.setdefault("country", country)
        if city:
            args.setdefault("city", city)
        need = args.get("information_need") or ClaimSearchPlanner.primary_information_need(state)
        if need:
            args.setdefault("information_need", need)
            args.setdefault("claim_type", need)
        args.setdefault("query", args.get("query") or state.raw_user_query)

    if tool_name in {"weather", "seasonality", "lodging"} or tool_name in {
        "openmeteo_mcp",
        "weather_mcp",
        "climate_mcp",
        "baidu_weather_mcp",
    }:
        if city and "city" not in args:
            args["city"] = city
        if country and "country" not in args:
            args["country"] = country
        if goal and goal.travel_date and "travel_date" not in args:
            args["travel_date"] = goal.travel_date
        from tools.mcp.adapters.baidu_response_parser import resolve_coordinates_from_evidence

        coords = resolve_coordinates_from_evidence(
            list(state.evidence),
            structured_result=state.structured_result,
        )
        if coords:
            args.setdefault("latitude", coords["latitude"])
            args.setdefault("longitude", coords["longitude"])

    if tool_name == "knowledge_prior":
        args.setdefault("raw_query", state.raw_user_query)
        if frame is not None:
            args.setdefault("semantic_frame", frame)
        args.setdefault("limitations", list(state.limitations))

    if tool_name == "fallback":
        args.setdefault("place_name", place_name or city or "unknown")
        args.setdefault("city", city)
        args.setdefault("country", country)
        args.setdefault("need_types", ["crowd_level"])

    if is_mcp_policy_tool(tool_name):
        if "query" not in args:
            args["query"] = state.raw_user_query
        if frame and frame.information_needs:
            args.setdefault("information_need", frame.information_needs[0])
        need = args.get("information_need") or ClaimSearchPlanner.primary_information_need(state)
        if need:
            args.setdefault("information_need", need)
        settings = get_settings()
        if tool_name in {"browser_mcp", "official_page_reader_mcp", "baidu_place_detail_mcp"}:
            domains = settings.official_page_domain_allowlist() or settings.browser_domain_allowlist()
            if domains:
                args.setdefault("allowed_domains", domains)
            if state.evidence and "url" not in args and "source_url" not in args:
                args.setdefault("prior_evidence", list(state.evidence))
            if tool_name == "baidu_place_detail_mcp" and "uid" not in args:
                from tools.mcp.adapters.baidu_response_parser import pick_baidu_uid_from_evidence

                uid = pick_baidu_uid_from_evidence(
                    list(state.evidence),
                    region=args.get("region") or (frame.entities.region if frame else None),
                    city=city,
                )
                if uid:
                    args.setdefault("uid", uid)
        if tool_name == "baidu_place_search_mcp":
            _enrich_baidu_search_arguments(args, state)
        if tool_name == "baidu_geocode_mcp":
            if place_name and "address" not in args and "query" not in args:
                args.setdefault("address", place_name)
        if tool_name in {"baidu_route_mcp", "baidu_route_matrix_mcp"}:
            _enrich_route_arguments(args, state, place_name=place_name, tool_name=tool_name)
        if tool_name == "baidu_ip_location_mcp":
            args["location_sensitive"] = True

    return args


def nearby_coordinate_patch(
    coords: dict[str, float] | None,
    *,
    radius: int = 3000,
) -> dict[str, object]:
    """MCP args patch: circle-based nearby search from anchor coordinates."""
    if not coords:
        return {}
    return {
        "nearby_search": True,
        "latitude": coords["latitude"],
        "longitude": coords["longitude"],
        "radius": radius,
    }


def apply_nearby_anchor_coordinates(
    args: dict,
    coords: dict[str, float] | None,
    *,
    radius: int = 3000,
) -> None:
    """Prefer lat/lng nearby search; drop region so Baidu uses location+radius."""
    if not coords:
        return
    args["nearby_search"] = True
    args["latitude"] = coords["latitude"]
    args["longitude"] = coords["longitude"]
    args["radius"] = radius
    args.pop("region", None)
    args.pop("bounds", None)


def _enrich_baidu_search_arguments(args: dict, state: TravelAgentState) -> None:
    raw_need = args.get("information_need") or ClaimSearchPlanner.primary_information_need(state)
    text = query_text_from_state(state)
    need = resolve_nearby_need(str(raw_need or ""), text=text)
    if need in BAIDU_TAG_BY_NEED and "tag" not in args:
        tag = baidu_tag_for_need(need) or BAIDU_TAG_BY_NEED.get(need)
        if tag:
            args["tag"] = tag
    if is_nearby_need(str(raw_need or "")) or is_nearby_need(need):
        suffix = nearby_query_suffix_for_need(need)
        if args.get("nearby_search") or (args.get("latitude") is not None and args.get("tag")):
            anchor = str(args.get("nearby_anchor_label") or args.get("place_name") or "").strip()
            if anchor and suffix:
                args["query"] = f"{anchor} {suffix}".strip()
        from tools.mcp.adapters.baidu_response_parser import resolve_nearby_anchor_coordinates

        coords = resolve_nearby_anchor_coordinates(
            list(state.evidence or []),
            user_query=state.raw_user_query or "",
            structured_result=state.structured_result,
        )
        if coords:
            apply_nearby_anchor_coordinates(args, coords)
    frame = state.semantic_frame
    if frame and frame.entities:
        has_coord_anchor = args.get("latitude") is not None and args.get("longitude") is not None
        if not has_coord_anchor and not args.get("region"):
            region = frame.entities.city or frame.entities.region
            if region:
                args.setdefault("region", region)


def _enrich_route_arguments(
    args: dict,
    state: TravelAgentState,
    *,
    place_name: str | None,
    tool_name: str,
) -> None:
    from app.orchestrator.evidence_signal_utils import is_day_trip_query

    frame = state.semantic_frame
    goal = state.user_goal
    dest = (
        args.get("destination")
        or args.get("to")
        or place_name
        or (frame.entities.places[0] if frame and frame.entities and frame.entities.places else None)
    )
    if dest:
        args.setdefault("destination", dest)
        args.setdefault("place_name", dest)
    origin = args.get("origin") or args.get("from")
    if not origin:
        origin = goal.start_location if goal and goal.start_location else None
    if not origin and frame and is_day_trip_query(frame):
        region = (frame.entities.region or "") if frame.entities else ""
        if region in ("新疆", "Xinjiang") or (
            frame.entities and frame.entities.country in ("China", "中国")
        ):
            origin = "乌鲁木齐市"
    if origin:
        args.setdefault("origin", origin)
    if tool_name == "baidu_route_matrix_mcp":
        args.setdefault("origins", origin)
        args.setdefault("destinations", dest)
