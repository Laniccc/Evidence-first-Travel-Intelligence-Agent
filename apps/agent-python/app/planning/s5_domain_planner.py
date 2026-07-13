"""Map ResponseContract claims + SemanticFrame to S5DomainPlan."""

from __future__ import annotations

import importlib
from typing import Any

from app.evidence.evidence_model import Evidence
from app.understanding.semantic_frame_model import SemanticFrame

from .s5_information_domain import InformationDomain, S5DomainPlan, S5DomainToolBinding, S5ToolRole
from .s5_information_domain_registry import S5_INFORMATION_DOMAIN_REGISTRY, bindings_for_domain


def _module(name: str):
    return importlib.import_module(name)


def _information_need_aliases():
    return _module("app.understanding.information_need_aliases")


def _is_nearby_need(need: str) -> bool:
    return _information_need_aliases().is_nearby_need(need)


def _normalize_need(need: str) -> str:
    return _information_need_aliases().normalize_need(need)


def _resolve_nearby_need(need: str, *, text: str = "") -> str:
    return _information_need_aliases().resolve_nearby_need(need, text=text)


def _resolve_lookup_need(need: str) -> str:
    return _module("app.understanding.lookup_need_aliases").resolve_lookup_need(need)


def _resolve_intent_strategy(intent_profile: Any) -> Any:
    return _module("app.planning.intent_strategy_registry").resolve_intent_strategy(intent_profile)


def _is_day_trip_query(frame: Any) -> bool:
    return _module("app.evidence.evidence_signal_utils").is_day_trip_query(frame)


def _is_evidence(value: Any) -> bool:
    return isinstance(value, Evidence)

D = InformationDomain

CLAIM_TO_DOMAINS: dict[str, list[InformationDomain]] = {
    "ticket_price": [D.TICKET_BOOKING, D.GEO_RESOLUTION],
    "ticket_price_candidate": [D.TICKET_BOOKING, D.GEO_RESOLUTION],
    "ticket_type": [D.TICKET_BOOKING, D.GEO_RESOLUTION],
    "discount_policy": [D.TICKET_BOOKING, D.GEO_RESOLUTION],
    "reservation_required": [D.TICKET_BOOKING, D.GEO_RESOLUTION],
    "reservation_policy": [D.TICKET_BOOKING, D.OPERATION_STATUS, D.GEO_RESOLUTION],
    "booking_channel": [D.TICKET_BOOKING, D.GEO_RESOLUTION],
    "opening_hours": [D.OPERATION_STATUS, D.GEO_RESOLUTION],
    "temporary_closure": [D.OPERATION_STATUS, D.GEO_RESOLUTION],
    "seasonal_operation_status": [D.OPERATION_STATUS, D.GEO_RESOLUTION],
    "road_opening_period": [D.OPERATION_STATUS, D.GEO_RESOLUTION],
    "daily_notice": [D.OPERATION_STATUS, D.GEO_RESOLUTION],
    "capacity_limit": [D.OPERATION_STATUS, D.GEO_RESOLUTION],
    "best_time_to_visit": [D.SEASONALITY, D.GEO_RESOLUTION],
    "seasonality": [D.SEASONALITY, D.GEO_RESOLUTION],
    "weather_by_month": [D.SEASONALITY, D.GEO_RESOLUTION],
    "scenery_by_month": [D.SEASONALITY, D.GEO_RESOLUTION],
    "crowd_by_season": [D.SEASONALITY, D.GEO_RESOLUTION],
    "flower_season": [D.SEASONALITY, D.GEO_RESOLUTION],
    "snow_season": [D.SEASONALITY, D.GEO_RESOLUTION],
    "autumn_foliage": [D.SEASONALITY, D.GEO_RESOLUTION],
    "road_condition_by_season": [D.SEASONALITY, D.GEO_RESOLUTION],
    "route_plan": [D.ROUTE_PLANNING, D.GEO_RESOLUTION],
    "transport_planning": [D.ROUTE_PLANNING, D.GEO_RESOLUTION],
    "itinerary_feasibility": [D.ROUTE_PLANNING, D.GEO_RESOLUTION],
    "distance": [D.ROUTE_PLANNING, D.GEO_RESOLUTION],
    "duration": [D.ROUTE_PLANNING, D.GEO_RESOLUTION],
    "route_steps": [D.ROUTE_PLANNING, D.GEO_RESOLUTION],
    "review_summary": [D.REVIEW_SIGNAL, D.GEO_RESOLUTION],
    "value_for_money": [D.REVIEW_SIGNAL, D.GEO_RESOLUTION],
    "elderly_suitability": [D.REVIEW_SIGNAL, D.GEO_RESOLUTION],
    "family_friendly": [D.REVIEW_SIGNAL, D.GEO_RESOLUTION],
    "commercialization_risk": [D.REVIEW_SIGNAL, D.GEO_RESOLUTION],
    "crowd_level": [D.REVIEW_SIGNAL, D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "crowd_risk": [D.REVIEW_SIGNAL, D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "queue_time": [D.REALTIME_STATUS, D.REVIEW_SIGNAL, D.GEO_RESOLUTION],
    "current_crowd": [D.REALTIME_STATUS, D.REVIEW_SIGNAL, D.GEO_RESOLUTION],
    "current_crowd_estimate": [D.REALTIME_STATUS, D.REVIEW_SIGNAL, D.GEO_RESOLUTION],
    "nearby_food": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_dining": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_restaurant": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_rest_area": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_poi": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_hotel": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_lodging": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_parking": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_toilet": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_station": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_attraction": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_accommodation": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "nearby_amenity": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "lodging_area": [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION],
    "today_weather": [D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "current_weather": [D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "forecast": [D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "weather": [D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "weather_today": [D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "weather_risk": [D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "traffic_status": [D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "congestion_risk": [D.REALTIME_STATUS, D.GEO_RESOLUTION],
    "road_traffic": [D.REALTIME_STATUS, D.ROUTE_PLANNING, D.GEO_RESOLUTION],
    "entity_resolution": [D.GEO_RESOLUTION],
    "place_lookup": [D.GEO_RESOLUTION],
    "coordinates": [D.GEO_RESOLUTION],
    "disambiguation": [D.GEO_RESOLUTION],
    "elevation": [D.GEO_FACT, D.GEO_RESOLUTION],
    "altitude": [D.GEO_FACT, D.GEO_RESOLUTION],
    "height_elevation": [D.GEO_FACT, D.GEO_RESOLUTION],
    "mountain_height": [D.GEO_FACT, D.GEO_RESOLUTION],
    "peak_height": [D.GEO_FACT, D.GEO_RESOLUTION],
    "area": [D.GEO_FACT, D.GEO_RESOLUTION],
    "highest_peak_elevation": [D.GEO_FACT, D.GEO_RESOLUTION],
    "main_peak_elevations": [D.GEO_FACT, D.GEO_RESOLUTION],
    "general_fact": [D.GEO_FACT, D.GEO_RESOLUTION],
}

_GEO_CLAIM_TYPES = frozenset(
    {
        "coordinates",
        "poi_uid",
        "resolved_address",
        "place_candidates",
    }
)

_ROUTE_CONTEXT_DECISIONS = frozenset(
    {"route_plan", "transport_planning", "how_to_choose", "nearby_search", "whether_to_go"}
)

_DAY_TRIP_ROUTE_CLAIMS = ("itinerary_feasibility", "distance", "duration", "transit")


class S5DomainPlanner:
    """Produce S5DomainPlan from contract claims and semantic frame."""

    def plan(
        self,
        contract: ResponseContract | None,
        frame: SemanticFrame | None,
        *,
        evidence: list | None = None,
        intent_profile: Any | None = None,
        intent_strategy: Any | None = None,
    ) -> S5DomainPlan:
        strategy = intent_strategy or (_resolve_intent_strategy(intent_profile) if intent_profile else None)
        claim_types = self._collect_claim_types(contract, frame)
        claim_types = self._inject_day_trip_claims(frame, claim_types)
        claim_to_domains: dict[str, list[InformationDomain]] = {}
        domain_set: set[InformationDomain] = set()

        frame_text = ""
        if frame:
            frame_text = f"{frame.raw_query} {frame.normalized_request}".strip()
        for claim in claim_types:
            canonical = _resolve_nearby_need(claim, text=frame_text)
            domains = list(CLAIM_TO_DOMAINS.get(canonical, CLAIM_TO_DOMAINS.get(claim, [])))
            if not domains and _is_nearby_need(claim):
                domains = [D.NEARBY_RECOMMENDATION, D.GEO_RESOLUTION]
            if claim in {"traffic_status", "congestion_risk"} and self._has_route_context(frame):
                if D.ROUTE_PLANNING not in domains:
                    domains.append(D.ROUTE_PLANNING)
            claim_to_domains[claim] = domains
            domain_set.update(domains)

        if self._needs_geo_prerequisite(frame, evidence):
            domain_set.add(D.GEO_RESOLUTION)
            for claim in claim_types:
                if D.GEO_RESOLUTION not in claim_to_domains.get(claim, []):
                    claim_to_domains.setdefault(claim, []).append(D.GEO_RESOLUTION)

        ordered_domains = self._order_domains(domain_set, strategy)
        bindings = self._collect_bindings(ordered_domains)

        notes: list[str] = []
        if D.GEO_RESOLUTION in domain_set and self._needs_geo_prerequisite(frame, evidence):
            notes.append("geo_resolution prerequisite: city/coordinates not yet resolved")

        retrieval_mode: str = "single_place"
        places = list(frame.entities.places) if frame and frame.entities else []
        if strategy and strategy.retrieval_mode == "multi_place_parallel":
            retrieval_mode = "multi_place_parallel"
        elif intent_profile and _intent_value(intent_profile.primary_intent) == "comparison":
            retrieval_mode = "multi_place_parallel"
        if retrieval_mode == "multi_place_parallel" and len(places) >= 2:
            notes.append(
                "comparison parallel retrieval: "
                + "; ".join(f"place={p}" for p in places[:6])
            )

        return S5DomainPlan(
            domains=ordered_domains,
            claim_to_domains=claim_to_domains,
            tool_bindings=bindings,
            notes=notes,
            intent_primary=_intent_value(intent_profile.primary_intent) if intent_profile else None,
            domain_priority=list(strategy.domain_priority) if strategy else [],
            retrieval_mode=retrieval_mode,  # type: ignore[arg-type]
        )

    @staticmethod
    def _inject_day_trip_claims(frame: SemanticFrame | None, claim_types: list[str]) -> list[str]:
        if not _is_day_trip_query(frame):
            return claim_types
        out = list(claim_types)
        for claim in _DAY_TRIP_ROUTE_CLAIMS:
            if claim not in out:
                out.append(claim)
        return out

    @staticmethod
    def _collect_claim_types(contract: ResponseContract | None, frame: SemanticFrame | None) -> list[str]:
        claims: list[str] = []
        frame_text = ""
        if frame:
            frame_text = f"{frame.raw_query} {frame.normalized_request}".strip()
        if contract:
            for req in contract.claim_requirements:
                canonical = _resolve_nearby_need(req.claim_type, text=frame_text)
                if canonical not in claims:
                    claims.append(canonical)
        if frame and frame.information_needs:
            for need in frame.information_needs:
                if _is_nearby_need(need):
                    canonical = _resolve_nearby_need(need, text=frame_text)
                else:
                    canonical = _resolve_lookup_need(_normalize_need(need))
                if canonical not in claims:
                    claims.append(canonical)
        return claims

    @staticmethod
    def _needs_geo_prerequisite(frame: SemanticFrame | None, evidence: list | None) -> bool:
        if frame and frame.entities and frame.entities.city:
            return False
        if evidence:
            for ev in evidence:
                if not _is_evidence(ev):
                    continue
                for claim in ev.claims:
                    ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
                    if ct in _GEO_CLAIM_TYPES:
                        return False
        return True

    @staticmethod
    def _has_route_context(frame: SemanticFrame | None) -> bool:
        if not frame:
            return False
        if _is_day_trip_query(frame):
            return True
        dt = frame.decision_type.value if frame.decision_type else ""
        if dt in _ROUTE_CONTEXT_DECISIONS:
            return True
        needs = set(frame.information_needs or [])
        return bool(needs & {"route_plan", "transport_planning", "itinerary_feasibility"})

    @staticmethod
    def _order_domains(
        domains: set[InformationDomain],
        strategy: Any | None = None,
    ) -> list[InformationDomain]:
        registry_order = list(S5_INFORMATION_DOMAIN_REGISTRY.keys())
        if not strategy or not strategy.domain_priority:
            return [d for d in registry_order if d in domains]
        priority = [d for d in strategy.domain_priority if d in domains]
        if D.GEO_RESOLUTION in domains and D.GEO_RESOLUTION not in priority:
            priority.insert(0, D.GEO_RESOLUTION)
        elif priority and priority[0] != D.GEO_RESOLUTION and D.GEO_RESOLUTION in domains:
            priority = [D.GEO_RESOLUTION] + [d for d in priority if d != D.GEO_RESOLUTION]
        tail = [d for d in registry_order if d in domains and d not in priority]
        return priority + tail

    @staticmethod
    def _collect_bindings(domains: list[InformationDomain]) -> list[S5DomainToolBinding]:
        seen: set[tuple[str, InformationDomain]] = set()
        result: list[S5DomainToolBinding] = []
        for domain in domains:
            for binding in bindings_for_domain(domain):
                key = (binding.tool_name, binding.domain)
                if key in seen:
                    continue
                seen.add(key)
                result.append(binding)
        return result

    @staticmethod
    def bindings_for_claim(claim_type: str) -> list[S5DomainToolBinding]:
        domains = CLAIM_TO_DOMAINS.get(claim_type, [])
        bindings: list[S5DomainToolBinding] = []
        for domain in domains:
            bindings.extend(bindings_for_domain(domain))
        return bindings

    @staticmethod
    def is_forbidden_binding(binding: S5DomainToolBinding) -> bool:
        return binding.role == S5ToolRole.FORBIDDEN


def _intent_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")
