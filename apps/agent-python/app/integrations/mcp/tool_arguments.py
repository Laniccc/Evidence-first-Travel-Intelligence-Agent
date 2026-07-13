"""Shared MCP argument enrichment for sub-agents and S5 CALL_TOOL."""

from __future__ import annotations

import importlib
import re
from typing import Any

from app.config import get_settings
from tools.ticketing.provider_config import is_ticket_provider_tool

TravelAgentState = Any


def _module(name: str):
    return importlib.import_module(name)


def _claim_search_planner():
    return _module("app.planning.claim_search_planner").ClaimSearchPlanner


def _information_need_aliases():
    return _module("app.understanding.information_need_aliases")


def is_nearby_need(need: str) -> bool:
    return _information_need_aliases().is_nearby_need(need)


def query_text_from_state(state: Any) -> str:
    return _information_need_aliases().query_text_from_state(state)


def resolve_nearby_need(need: str, *, text: str = "") -> str:
    return _information_need_aliases().resolve_nearby_need(need, text=text)


def is_mcp_policy_tool(tool_name: str) -> bool:
    return _module("app.tools.tool_name_resolver").is_mcp_policy_tool(tool_name)


def _is_valid_baidu_uid(uid: str | None) -> bool:
    from tools.mcp.adapters.baidu_response_parser import is_valid_baidu_uid

    return is_valid_baidu_uid(uid)


def _is_ticket_price_lookup(state: TravelAgentState) -> bool:
    policy = _module("app.orchestration.fact_lookup_policy")
    return policy.is_fact_lookup_task(state) and policy.primary_fact_need_from_state(state) == "ticket_price"


def _enrich_official_page_reader_arguments(args: dict, state: TravelAgentState) -> None:
    from tools.official_source.url_normalizer import is_official_reader_url

    primary_fact_need_from_state = _module(
        "app.orchestration.fact_lookup_policy"
    ).primary_fact_need_from_state
    official_candidates = _module("app.evidence.official_candidate_bridge")
    need = str(args.get("information_need") or primary_fact_need_from_state(state) or "").strip()
    ticket_needs = {
        "ticket_price",
        "entrance_ticket_price",
        "boat_ticket_price",
        "shuttle_bus_ticket_price",
        "cable_car_ticket_price",
        "opening_hours",
        "reservation_policy",
        "temporary_closure",
    }
    if need in ticket_needs:
        args["information_need"] = need
        args.setdefault("max_follow_urls", 5)

    readable_urls = official_candidates.collect_readable_urls_for_claim(state, need or None)
    best = official_candidates.best_official_url(state, need or None)
    if best:
        args.setdefault("url", best)
    if readable_urls:
        filtered = [u for u in readable_urls if is_official_reader_url(u)]
        if filtered:
            args.setdefault("urls", filtered[:5])
            if not args.get("url"):
                args.setdefault("url", filtered[0])


def _apply_coordinate_defaults(args: dict, state: TravelAgentState) -> None:
    from tools.mcp.adapters.baidu_response_parser import resolve_coordinates_from_evidence

    coords = resolve_coordinates_from_evidence(
        list(state.evidence),
        structured_result=state.structured_result,
    )
    if coords:
        args.setdefault("latitude", coords["latitude"])
        args.setdefault("longitude", coords["longitude"])


def _route_endpoints_from_text(text: str) -> tuple[str | None, str | None]:
    """Parse common Chinese route phrasing: 从A到B..."""
    raw = str(text or "").strip()
    if not raw:
        return None, None
    match = re.search(
        r"从(?P<origin>.+?)到(?P<dest>.+?)(?:坐|打|开|怎么|大概|大约|多久|多长|路线|$)",
        raw,
    )
    if not match:
        return None, None
    origin = re.sub(r"[，,。?？!！\s]+$", "", match.group("origin")).strip()
    dest = re.sub(r"[，,。?？!！\s]+$", "", match.group("dest")).strip()
    return (origin or None), (dest or None)


def mcp_tool_invocation_ready(
    tool_name: str,
    arguments: dict,
    *,
    state: TravelAgentState,
    prompt_context: dict | None = None,
) -> bool:
    """True when enrich + validation would succeed for this tool/state."""
    try:
        enrich_mcp_tool_arguments(
            tool_name,
            dict(arguments),
            state=state,
            prompt_context=prompt_context,
        )
        return True
    except ValueError:
        return False


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
    if prompt_context.get("gap_filling"):
        gap_parameters = (prompt_context.get("gap_request") or {}).get("tool_parameters") or {}
        for key, value in gap_parameters.items():
            args.setdefault(key, value)
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
        if frame and frame.entities and frame.entities.region:
            args.setdefault("province", frame.entities.region)
        if _is_ticket_price_lookup(state):
            args["information_need"] = "ticket_price"
            args["claim_type"] = "ticket_price"
        else:
            need = args.get("information_need") or _claim_search_planner().primary_information_need(state)
            if need:
                args.setdefault("information_need", need)
                args.setdefault("claim_type", need)
        args.setdefault("query", args.get("query") or state.raw_user_query)
        ticket_product_policy = _module("app.planning.ticket_product_policy")
        product_ctx = ticket_product_policy.ensure_ticket_product_context(state)
        if product_ctx:
            args.setdefault("ticket_product", product_ctx.get("ticket_product"))
            place_aliases = ticket_product_policy.place_aliases_for_ticket(state)
            product_kws = ticket_product_policy.product_keywords_for_ticket(state)
            if product_kws:
                args["product_keywords"] = product_kws
                args["ticket_product_keywords"] = product_kws
            if place_aliases:
                args["place_aliases"] = place_aliases
                args["aliases"] = place_aliases[:12]
            place = args.get("place_name") or resolved_place_label(state)
            if place:
                args.setdefault("normalized_place", place)
            if product_kws:
                product_query = " ".join(product_kws[:4])
                if product_query and product_query not in (args.get("query") or ""):
                    args["query"] = f"{args.get('query') or state.raw_user_query} {product_query}".strip()
        build_ticket_place_aliases = _module(
            "app.planning.ticket_lookup_helpers"
        ).build_ticket_place_aliases
        resolved_place_label = _module(
            "app.orchestration.fact_lookup_anchor_policy"
        ).resolved_place_label

        if not args.get("aliases"):
            aliases = build_ticket_place_aliases(state)
            if aliases:
                args.setdefault("aliases", aliases)

    if tool_name == "official_source_discovery_mcp":
        ticket_lookup_helpers = _module("app.planning.ticket_lookup_helpers")
        hits, urls = ticket_lookup_helpers.collect_official_discovery_search_results(state)
        if hits:
            args.setdefault("search_results", hits)
        if urls:
            args.setdefault("urls", urls)
        ticket_product_policy = _module("app.planning.ticket_product_policy")
        ticket_relevance_policy = _module("app.evidence.ticket_relevance_policy")
        place = str(args.get("place_name") or "").strip()
        claim = args.get("claim_type") or args.get("information_need")
        anchors = ticket_relevance_policy.place_anchor_terms(state)
        product_ctx = ticket_product_policy.ensure_ticket_product_context(state)
        ticket_product = (product_ctx or {}).get("ticket_product") if product_ctx else None
        if hits:
            hits = [
                h
                for h in hits
                if ticket_relevance_policy.discovery_hit_relevant(
                    h,
                    place_name=place,
                    claim_type=str(claim) if claim else None,
                    anchor_terms=anchors,
                    ticket_product=ticket_product,
                )
            ]
            args["search_results"] = hits
        if urls:
            urls = [
                u
                for u in urls
                if ticket_relevance_policy.discovery_hit_relevant(
                    {"url": u, "title": "", "snippet": ""},
                    place_name=place,
                    claim_type=str(claim) if claim else None,
                    anchor_terms=anchors,
                    ticket_product=ticket_product,
                )
            ]
            args["urls"] = urls
        args.setdefault("anchor_terms", anchors)
        if state.evidence:
            args.setdefault("prior_evidence", list(state.evidence))

    if tool_name == "search_mcp":
        from tools.mcp.adapters.search_mcp_adapter import SearchMCPAdapter

        limit = SearchMCPAdapter.resolve_search_limit(args)
        args["limit"] = limit
        args.setdefault("top_k", limit)
        args.setdefault("max_results", limit)

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

        _apply_coordinate_defaults(args, state)

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

    if tool_name == "baidu_traffic_mcp":
        args.setdefault("model", "road")
        if not args.get("road_name") and not args.get("road"):
            text = state.raw_user_query or ""
            if re.search(r"路况|拥堵|堵|道路|公路|高速", text):
                args.setdefault("road_name", args.get("query") or text)

    if is_mcp_policy_tool(tool_name):
        if "query" not in args:
            args["query"] = state.raw_user_query
        if frame and frame.information_needs:
            args.setdefault("information_need", frame.information_needs[0])
        need = args.get("information_need") or _claim_search_planner().primary_information_need(state)
        if need:
            args.setdefault("information_need", need)
        settings = get_settings()
        if tool_name in {"browser_mcp", "official_page_reader_mcp", "baidu_place_detail_mcp"}:
            domains = settings.official_page_domain_allowlist() or settings.browser_domain_allowlist()
            if domains:
                args.setdefault("allowed_domains", domains)
            if state.evidence and "url" not in args and "source_url" not in args:
                args.setdefault("prior_evidence", list(state.evidence))
            if tool_name == "official_page_reader_mcp":
                _enrich_official_page_reader_arguments(args, state)
            elif tool_name == "browser_mcp":
                readable_urls = _module(
                    "app.evidence.official_candidate_bridge"
                ).collect_readable_urls_for_claim(state)
                if readable_urls:
                    args.setdefault("urls", readable_urls[:5])
                    args.setdefault("url", readable_urls[0])
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
        if tool_name == "baidu_reverse_geocode_mcp":
            _apply_coordinate_defaults(args, state)

    _validate_mcp_tool_arguments(tool_name, args, state=state)
    return args


def _validate_mcp_tool_arguments(tool_name: str, args: dict, *, state: TravelAgentState) -> None:
    """Raise ValueError when required args cannot be satisfied (post-enrichment)."""
    if tool_name == "baidu_route_matrix_mcp":
        origin, dest = _route_endpoints_from_text(state.raw_user_query)
        if origin and dest:
            raise ValueError("baidu_route_matrix_mcp skipped for one-to-one route; use baidu_route_mcp")
    if tool_name == "baidu_traffic_mcp":
        text = state.raw_user_query or ""
        if not (args.get("road_name") or args.get("road")):
            raise ValueError("baidu_traffic_mcp requires a road_name or explicit traffic query")
        if not re.search(r"路况|拥堵|堵|道路|公路|高速", text):
            raise ValueError("baidu_traffic_mcp skipped when user did not ask traffic status")
    if tool_name == "official_source_discovery_mcp":
        urls = list(args.get("urls") or [])
        hits = list(args.get("search_results") or [])
        if not urls and not hits:
            raise ValueError(
                "official_source_discovery_mcp requires urls or search_results; skip when none available"
            )
    if tool_name == "baidu_reverse_geocode_mcp":
        if args.get("latitude") is None or args.get("longitude") is None:
            raise ValueError("baidu_reverse_geocode_mcp requires latitude and longitude")
    if tool_name == "baidu_place_detail_mcp":
        uid = str(args.get("uid") or "").strip()
        if uid and not _is_valid_baidu_uid(uid):
            args.pop("uid", None)
    if tool_name in {"official_page_reader_mcp", "browser_mcp"}:
        url = str(args.get("url") or args.get("source_url") or "").strip()
        urls = [str(u).strip() for u in (args.get("urls") or []) if str(u).strip()]
        if tool_name == "official_page_reader_mcp":
            from tools.official_source.url_normalizer import is_official_reader_url

            urls = [u for u in urls if is_official_reader_url(u)]
            if url and not is_official_reader_url(url):
                url = ""
                args.pop("url", None)
                args.pop("source_url", None)
            if urls:
                args["urls"] = urls
                args.setdefault("url", urls[0])
        if not url and not urls:
            raise ValueError(f"{tool_name} requires a readable url")


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
    raw_need = args.get("information_need") or _claim_search_planner().primary_information_need(state)
    text = query_text_from_state(state)
    need = resolve_nearby_need(str(raw_need or ""), text=text)
    nearby_policy = _module("app.evidence.nearby_recommendation_policy")
    if need in nearby_policy.BAIDU_TAG_BY_NEED and "tag" not in args:
        tag = nearby_policy.baidu_tag_for_need(need) or nearby_policy.BAIDU_TAG_BY_NEED.get(need)
        if tag:
            args["tag"] = tag
    if is_nearby_need(str(raw_need or "")) or is_nearby_need(need):
        suffix = nearby_policy.nearby_query_suffix_for_need(need)
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
    is_day_trip_query = _module(
        "app.evidence.evidence_signal_utils"
    ).is_day_trip_query

    frame = state.semantic_frame
    goal = state.user_goal
    parsed_origin, parsed_dest = _route_endpoints_from_text(state.raw_user_query)
    dest = (
        args.get("destination")
        or args.get("to")
        or parsed_dest
        or place_name
        or (frame.entities.places[0] if frame and frame.entities and frame.entities.places else None)
    )
    if dest:
        args.setdefault("destination", dest)
        args.setdefault("place_name", dest)
    origin = args.get("origin") or args.get("from")
    if not origin:
        origin = parsed_origin
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
        if origin:
            args.setdefault("origins", origin)
        if dest:
            args.setdefault("destinations", dest)
    if re.search(r"地铁|公交|换乘", state.raw_user_query or ""):
        args.setdefault("mode", "transit")
    elif re.search(r"打车|出租车|网约车|开车|驾车", state.raw_user_query or ""):
        args.setdefault("mode", "driving")
