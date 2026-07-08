"""Check evidence coverage against ResponseContract claim requirements."""

from __future__ import annotations

import re

from app.schemas.coverage_report import CoverageItem, CoverageReport
from app.schemas.evidence import ClaimType, Evidence, SourceType
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.tool_trace import ToolTrace
from app.orchestrator.information_need_aliases import is_nearby_need
from app.orchestrator.nearby_recommendation_policy import (
    claim_aliases_for_need,
    is_nearby_information_need,
    place_candidates_is_nearby_recommendation,
)
from app.orchestrator.official_source_judgement import best_official_support, parse_candidate_from_evidence
from app.orchestrator.ticket_lookup_helpers import is_ticket_price_noise_evidence, ticket_platform_candidate_quality
from app.tools.tool_name_resolver import resolve_tool_name

_GENERIC_TEMPLATE_PATTERNS = re.compile(
    r"建议查阅|旅游局|气候资料|无法确认|没有具体|需进一步查询|请查询官方",
    re.I,
)

_CLAIM_TYPE_ALIASES: dict[str, frozenset[str]] = {
    "ticket_price": frozenset(
        {
            ClaimType.TICKET_PRICE.value,
            ClaimType.PRICE_CANDIDATE.value,
            ClaimType.TICKET_PRICE_CANDIDATE.value,
            "price_candidate",
        }
    ),
    "booking_channel": frozenset({ClaimType.BOOKING_CHANNEL.value}),
    "historical_ticket_price": frozenset(
        {ClaimType.HISTORICAL_TICKET_SNAPSHOT.value, ClaimType.TICKET_PRICE_HISTORY.value}
    ),
    "opening_hours": frozenset(
        {ClaimType.OPENING_HOURS.value, ClaimType.OPENING_HOURS_CANDIDATE.value}
    ),
    "weather_today": frozenset({ClaimType.WEATHER.value, "weather"}),
    "forecast": frozenset({ClaimType.WEATHER.value, "weather"}),
    "weather": frozenset({ClaimType.WEATHER.value}),
    "current_crowd": frozenset({ClaimType.CROWD.value}),
    "queue_time": frozenset({ClaimType.CROWD.value}),
    "crowd_level": frozenset({ClaimType.CROWD.value}),
    "best_time_to_visit": frozenset(
        {
            ClaimType.BEST_TIME_TO_VISIT.value,
            ClaimType.SEASONALITY.value,
            ClaimType.TRAVEL_ADVICE.value,
        }
    ),
    "seasonality": frozenset({ClaimType.SEASONALITY.value, ClaimType.TRAVEL_ADVICE.value}),
    "seasonal_operation_status": frozenset(
        {
            ClaimType.SEASONAL_OPERATION_STATUS.value,
            ClaimType.ROAD_OPENING_PERIOD.value,
            ClaimType.PUBLIC_NOTICE.value,
            ClaimType.OPENING_HOURS.value,
        }
    ),
    "general_seasonal_context": frozenset(
        {ClaimType.GENERAL_SEASONAL_CONTEXT.value, ClaimType.SEASONALITY.value, ClaimType.TRAVEL_ADVICE.value}
    ),
    "route_plan": frozenset(
        {
            ClaimType.ROUTE_STEPS.value,
            ClaimType.DISTANCE.value,
            ClaimType.DURATION.value,
        }
    ),
    "transport_planning": frozenset(
        {
            ClaimType.ROUTE_STEPS.value,
            ClaimType.DISTANCE.value,
            ClaimType.DURATION.value,
        }
    ),
    "road_traffic": frozenset({ClaimType.TRAFFIC_STATUS.value}),
    "traffic_status": frozenset({ClaimType.TRAFFIC_STATUS.value}),
    "congestion_risk": frozenset({ClaimType.CONGESTION_RISK.value, ClaimType.TRAFFIC_STATUS.value}),
    "user_location": frozenset(
        {ClaimType.INFERRED_CITY.value, ClaimType.USER_LOCATION_ESTIMATION.value}
    ),
    "entity_resolution": frozenset(
        {ClaimType.PLACE_CANDIDATES.value, ClaimType.COORDINATES.value, ClaimType.POI_UID.value}
    ),
    "nearby_food": frozenset(
        {
            ClaimType.FOOD.value,
            ClaimType.GENERAL_FACT.value,
            ClaimType.RATING_CANDIDATE.value,
            ClaimType.ADDRESS.value,
        }
    ),
    "nearby_hotel": frozenset(
        {
            ClaimType.LODGING.value,
            ClaimType.GENERAL_FACT.value,
            ClaimType.RATING_CANDIDATE.value,
            ClaimType.ADDRESS.value,
        }
    ),
    "nearby_poi": frozenset(
        {
            ClaimType.GENERAL_FACT.value,
            ClaimType.ADDRESS.value,
            ClaimType.RATING_CANDIDATE.value,
        }
    ),
    "nearby_toilet": frozenset({ClaimType.GENERAL_FACT.value, ClaimType.ADDRESS.value}),
    "nearby_parking": frozenset({ClaimType.GENERAL_FACT.value, ClaimType.ADDRESS.value}),
    "nearby_rest_area": frozenset({ClaimType.GENERAL_FACT.value, ClaimType.ADDRESS.value}),
    "nearby_station": frozenset({ClaimType.GENERAL_FACT.value, ClaimType.ADDRESS.value}),
    "elevation": frozenset(
        {
            ClaimType.ELEVATION.value,
            ClaimType.GENERAL_FACT.value,
        }
    ),
}

_ELEVATION_VALUE_PATTERN = re.compile(
    r"海拔\s*[:：]?\s*\d{3,4}(?:\.\d+)?\s*米|"
    r"\d{3,4}(?:\.\d+)?\s*米.{0,12}海拔|"
    r"elevation\s*[:=]?\s*\d{3,4}",
    re.I,
)
_ELEVATION_NOISE_PATTERN = re.compile(
    r"平方千米|经纬度|总面积|南北长约|东西宽约|开放时间|门票|营业时间",
    re.I,
)

_FINISH_OPTIONAL_TOOLS = frozenset(
    {
        "fallback",
        "knowledge_prior",
        "climate_mcp",
        "ticket_price_history_query",
        "ticket_snapshot_store",
        "fliggy_ticket_snapshot_crawler_mcp",
        "ticketlens_experience_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
    }
)

_HARD_FACT_PRIMARY_TOOLS: dict[str, list[str]] = {
    "elevation": ["wikidata_mcp", "wikipedia_mcp", "search_mcp", "browser_mcp"],
    "ticket_price": [
        "search_mcp",
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
    ],
    "opening_hours": ["search_mcp", "official_page_reader_mcp", "official_source_discovery_mcp"],
}

_IRRELEVANT_FINISH_FOR_NEARBY = frozenset(
    {
        "baidu_route_mcp",
        "baidu_route_matrix_mcp",
        "baidu_traffic_mcp",
        "baidu_reverse_geocode_mcp",
        "wikipedia_mcp",
        "wikidata_mcp",
        "osm_mcp",
        "climate_mcp",
        "knowledge_prior",
    }
)

_GEO_ONLY_CLAIMS = frozenset(
    {
        ClaimType.PLACE_CANDIDATES.value,
        ClaimType.COORDINATES.value,
        ClaimType.POI_UID.value,
        ClaimType.RESOLVED_ADDRESS.value,
        ClaimType.ADDRESS.value,
    }
)

_REVIEW_EXPERIENCE_CLAIMS = frozenset(
    {
        "review_summary",
        "value_for_money",
        "elderly_suitability",
        "family_friendly",
        "commercialization_risk",
        "review_aspect",
        ClaimType.REVIEW_ASPECT.value,
    }
)

_ROUTE_ONLY_CLAIMS = frozenset(
    {
        "route_plan",
        "transport_planning",
        "route_steps",
        ClaimType.ROUTE_STEPS.value,
        ClaimType.DISTANCE.value,
        ClaimType.DURATION.value,
    }
)

_IRRELEVANT_FOR: dict[str, frozenset[str]] = {
    "ticket_price": frozenset(
        {
            ClaimType.CROWD.value,
            ClaimType.WEATHER.value,
            *_GEO_ONLY_CLAIMS,
            ClaimType.REVIEW_ASPECT.value,
            ClaimType.REVIEW_SUMMARY.value,
            ClaimType.TICKET_RELATED_MENTIONS.value,
            ClaimType.ROUTE_STEPS.value,
        }
    ),
    "opening_hours": frozenset({ClaimType.CROWD.value, ClaimType.WEATHER.value, *_GEO_ONLY_CLAIMS}),
    "best_time_to_visit": frozenset(
        {
            ClaimType.CROWD.value,
            ClaimType.TICKET_PRICE.value,
            ClaimType.WEATHER.value,
            *_GEO_ONLY_CLAIMS,
            ClaimType.ROUTE_STEPS.value,
        }
    ),
    "seasonality": frozenset(
        {
            ClaimType.WEATHER.value,
            ClaimType.TICKET_PRICE.value,
            *_GEO_ONLY_CLAIMS,
        }
    ),
    "seasonal_operation_status": frozenset(
        {ClaimType.CROWD.value, ClaimType.GENERAL_SEASONAL_CONTEXT.value, *_GEO_ONLY_CLAIMS}
    ),
    "elevation": frozenset(
        {
            ClaimType.TICKET_PRICE.value,
            ClaimType.OPENING_HOURS.value,
            ClaimType.CROWD.value,
            ClaimType.WEATHER.value,
            ClaimType.PLACE_CANDIDATES.value,
            ClaimType.COORDINATES.value,
            ClaimType.POI_UID.value,
            ClaimType.RESOLVED_ADDRESS.value,
        }
    ),
    "forecast": frozenset({ClaimType.SEASONALITY.value, ClaimType.BEST_TIME_TO_VISIT.value}),
    "weather": frozenset({ClaimType.SEASONALITY.value, ClaimType.BEST_TIME_TO_VISIT.value}),
    "weather_today": frozenset({ClaimType.SEASONALITY.value, ClaimType.BEST_TIME_TO_VISIT.value}),
    "current_weather": frozenset({ClaimType.SEASONALITY.value, ClaimType.BEST_TIME_TO_VISIT.value}),
    "value_for_money": frozenset(
        {ClaimType.TICKET_PRICE.value, ClaimType.OPENING_HOURS.value, ClaimType.ROUTE_STEPS.value}
    ),
    "elderly_suitability": frozenset(
        {ClaimType.TICKET_PRICE.value, ClaimType.OPENING_HOURS.value, ClaimType.ROUTE_STEPS.value}
    ),
}


class EvidenceCoverageChecker:
    """Map evidence + tool traces to CoverageReport."""

    def check(
        self,
        contract: ResponseContract,
        evidence: list,
        tool_traces: list[ToolTrace],
    ) -> CoverageReport:
        items: list[CoverageItem] = []
        for req in contract.claim_requirements:
            items.append(self._evaluate_claim(req, evidence, tool_traces))

        required = [i for i, r in zip(items, contract.claim_requirements) if r.priority == "required"]
        all_required = all(i.covered for i in required) if required else True
        untried = self._untried_required_primary_tools(contract, tool_traces, items)
        # S5 finish is governed by RetrievalAttemptLedger; coverage is S7's job.
        can_finish = True

        need_limits = any(
            not i.covered and contract.claim_requirements[idx].priority == "required"
            for idx, i in enumerate(items)
        )

        summary_parts = [
            f"{i.claim_type}:{'ok' if i.covered else 'missing'}({i.coverage_quality})"
            for i in items
        ]
        return CoverageReport(
            items=items,
            all_required_covered=all_required,
            can_finish_evidence_planning=can_finish,
            answer_should_include_limitations=need_limits,
            summary="; ".join(summary_parts),
        )

    def _evaluate_claim(
        self,
        req: ClaimRequirement,
        evidence: list,
        tool_traces: list[ToolTrace],
    ) -> CoverageItem:
        aliases = _CLAIM_TYPE_ALIASES.get(req.claim_type, frozenset({req.claim_type}))
        if is_nearby_information_need(req.claim_type):
            aliases = claim_aliases_for_need(req.claim_type)
        irrelevant = _IRRELEVANT_FOR.get(req.claim_type, frozenset())

        matched_ids: list[str] = []
        best_quality = "none"
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            if req.claim_type == "ticket_price" and is_ticket_price_noise_evidence(ev, claim_type=req.claim_type):
                continue
            for claim in ev.claims:
                ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
                if ct in irrelevant:
                    continue
                if ct not in aliases and req.claim_type not in ct:
                    continue
                if req.claim_type == "seasonal_operation_status" and ct == ClaimType.GENERAL_SEASONAL_CONTEXT.value:
                    continue
                if req.claim_type == "seasonal_operation_status" and ev.source_type.value == "model_prior":
                    continue
                if req.claim_type == "ticket_price" and ct in {
                    ClaimType.PRICE_CANDIDATE.value,
                    ClaimType.TICKET_PRICE_CANDIDATE.value,
                }:
                    matched_ids.append(ev.evidence_id)
                    if self._quality_rank("partial") > self._quality_rank(best_quality):
                        best_quality = "partial"
                    continue
                if ct in _GEO_ONLY_CLAIMS and req.claim_type not in {
                    "entity_resolution",
                    "place_lookup",
                    "coordinates",
                    "disambiguation",
                }:
                    if (
                        is_nearby_information_need(req.claim_type)
                        and ct == ClaimType.PLACE_CANDIDATES.value
                        and place_candidates_is_nearby_recommendation(claim)
                    ):
                        pass
                    else:
                        continue
                if req.claim_type in _REVIEW_EXPERIENCE_CLAIMS and ct in {
                    ClaimType.TICKET_PRICE.value,
                    ClaimType.OPENING_HOURS.value,
                    ClaimType.PRICE_CANDIDATE.value,
                }:
                    continue
                if req.claim_type in _ROUTE_ONLY_CLAIMS and ct == ClaimType.REVIEW_ASPECT.value:
                    continue
                if req.claim_type in {"best_time_to_visit", "seasonality"} and ct == ClaimType.WEATHER.value:
                    continue
                if req.claim_type in {"ticket_price", "seasonal_operation_status", "best_time_to_visit"}:
                    if ev.source_type == SourceType.UNKNOWN and "fallback" in (ev.source_name or "").lower():
                        continue
                    if ev.source_type.value == "fallback":
                        continue
                quality = self._quality_for_claim(req, claim, ev)
                if quality == "none":
                    continue
                matched_ids.append(ev.evidence_id)
                if self._quality_rank(quality) > self._quality_rank(best_quality):
                    best_quality = quality

        covered = best_quality in ("partial", "strong") or (
            req.priority == "optional" and best_quality == "weak"
        )
        if req.priority == "required" and req.claim_type == "ticket_price" and best_quality != "strong":
            support = best_official_support(evidence, req.claim_type)
            if support.tier != "strong":
                covered = False
        elif req.priority == "required" and best_quality not in ("partial", "strong"):
            covered = False
        elif req.claim_type == "elevation" and req.requires_exact_fact:
            from app.orchestrator.peak_elevation_extraction import classify_elevation_text

            if best_quality == "partial":
                blob = " ".join(
                    f"{getattr(c, 'value', '')} {getattr(c, 'raw_text', '')}"
                    for ev in evidence
                    if isinstance(ev, Evidence)
                    for c in ev.claims
                    if ev.evidence_id in matched_ids
                )
                if classify_elevation_text(blob) == "range_only":
                    covered = False

        missing_reason = None
        if not covered:
            tried = [t.tool_name for t in tool_traces if t.status in ("ok", "error")]
            missing_reason = (
                f"No qualifying evidence for {req.claim_type}; tried: {', '.join(tried) or 'none'}"
            )

        return CoverageItem(
            claim_type=req.claim_type,
            covered=covered,
            evidence_ids=matched_ids,
            missing_reason=missing_reason,
            coverage_quality=best_quality,  # type: ignore[arg-type]
            can_answer=covered or req.priority == "optional",
            missing_behavior=req.missing_behavior,
        )

    def _quality_for_claim(self, req: ClaimRequirement, claim, ev: Evidence) -> str:
        text = f"{claim.value or ''} {claim.raw_text or ''}"
        if req.claim_type in ("best_time_to_visit", "seasonality"):
            if _GENERIC_TEMPLATE_PATTERNS.search(text):
                return "weak"
            if not re.search(r"\d{1,2}月|春|夏|秋|冬|season|month", text, re.I):
                return "weak"
        if req.claim_type == "seasonal_operation_status":
            if _GENERIC_TEMPLATE_PATTERNS.search(text) and not re.search(
                r"\d{1,2}月|至|到|-", text
            ):
                return "weak"
            if re.search(r"\d{1,2}月", text):
                return "strong"
            return "partial"
        if req.claim_type == "ticket_price" and claim.claim_type.value in {
            ClaimType.PRICE_CANDIDATE.value,
            ClaimType.TICKET_PRICE_CANDIDATE.value,
        }:
            if is_ticket_price_noise_evidence(ev, claim_type=req.claim_type):
                return "none"
            return ticket_platform_candidate_quality(ev) or "partial"
        if req.claim_type == "ticket_price" and claim.claim_type.value == ClaimType.TICKET_PRICE.value:
            if is_ticket_price_noise_evidence(ev, claim_type=req.claim_type):
                return "none"
            support = best_official_support([ev], req.claim_type)
            if support.tier == "strong":
                return "strong"
            if support.tier == "partial":
                return "partial"
            return "partial"
        if req.claim_type == "ticket_price":
            support = best_official_support([ev], req.claim_type)
            if claim.claim_type.value == ClaimType.OFFICIAL_SOURCE_CANDIDATE.value:
                if support.tier == "strong":
                    return "strong"
                if support.tier == "partial":
                    return "partial"
                if support.tier == "weak":
                    return "weak"
                return "none"
        if req.claim_type in _REVIEW_EXPERIENCE_CLAIMS and claim.claim_type.value == ClaimType.REVIEW_SUMMARY.value:
            return "strong"
        if req.claim_type == "booking_channel" and claim.claim_type.value == ClaimType.BOOKING_CHANNEL.value:
            if ev.source_type in {SourceType.OFFICIAL, SourceType.TICKET_PLATFORM}:
                return "strong"
            return "partial"
        if req.claim_type == "historical_ticket_price" and claim.claim_type.value in {
            ClaimType.HISTORICAL_TICKET_SNAPSHOT.value,
            ClaimType.TICKET_PRICE_HISTORY.value,
        }:
            return "strong"
        if req.claim_type == "elevation":
            from app.orchestrator.peak_elevation_extraction import classify_elevation_text

            gran = classify_elevation_text(text)
            if gran == "unrelated_geo":
                return "none"
            if gran == "range_only":
                return "partial"
            if gran == "exact_numeric":
                source = (ev.source_name or "").lower()
                if ev.source_type == SourceType.OFFICIAL:
                    return "strong"
                if any(x in source for x in ("wikidata", "wikipedia", "百科", "encyclopedia")):
                    return "strong"
                if claim.claim_type.value == ClaimType.ELEVATION.value:
                    return "strong"
                return "partial"
            if _ELEVATION_NOISE_PATTERN.search(text) and not _ELEVATION_VALUE_PATTERN.search(text):
                return "none"
            if _ELEVATION_VALUE_PATTERN.search(text):
                source = (ev.source_name or "").lower()
                if ev.source_type == SourceType.OFFICIAL:
                    return "strong"
                if any(x in source for x in ("wikidata", "wikipedia", "百科", "encyclopedia")):
                    return "strong"
                if claim.claim_type.value == ClaimType.ELEVATION.value:
                    return "strong"
                return "partial"
            if claim.claim_type.value == ClaimType.ELEVATION.value and re.search(r"\d{3,4}", text):
                return "partial"
        if ev.source_type.value == "model_prior" and not req.model_prior_allowed:
            return "none"
        conf = getattr(claim, "confidence", 0.5) or 0.5
        if conf >= 0.65:
            return "strong"
        if conf >= 0.45:
            return "partial"
        return "weak"

    @staticmethod
    def _quality_rank(q: str) -> int:
        return {"none": 0, "weak": 1, "partial": 2, "strong": 3}.get(q, 0)

    @staticmethod
    def _untried_required_primary_tools(
        contract: ResponseContract,
        tool_traces: list[ToolTrace],
        items: list[CoverageItem],
    ) -> list[str]:
        called = {resolve_tool_name(t.tool_name) for t in tool_traces}
        pending: list[str] = []
        for req, item in zip(contract.claim_requirements, items):
            if req.priority != "required" or item.covered:
                continue
            primaries = _HARD_FACT_PRIMARY_TOOLS.get(req.claim_type)
            if primaries:
                if any(resolve_tool_name(tool) in called for tool in primaries):
                    continue
                for tool in primaries:
                    resolved = resolve_tool_name(tool)
                    if resolved not in called:
                        pending.append(tool)
                        break
                continue
            for tool in req.preferred_tools[:4]:
                resolved = resolve_tool_name(tool)
                if resolved in _FINISH_OPTIONAL_TOOLS:
                    continue
                if is_nearby_need(req.claim_type) and resolved in _IRRELEVANT_FINISH_FOR_NEARBY:
                    continue
                if resolved not in called:
                    pending.append(tool)
                    break
        for tool in contract.entity_policy.preferred_tools:
            resolved = resolve_tool_name(tool)
            if resolved in _FINISH_OPTIONAL_TOOLS:
                continue
            if tool not in pending and resolved not in called:
                pending.append(tool)
        return pending

    @staticmethod
    def _untried_preferred_tools(
        contract: ResponseContract,
        tool_traces: list[ToolTrace],
    ) -> list[str]:
        called = {resolve_tool_name(t.tool_name) for t in tool_traces}
        pending: list[str] = []
        for req in contract.claim_requirements:
            if req.priority != "required":
                continue
            for tool in req.preferred_tools:
                resolved = resolve_tool_name(tool)
                if is_nearby_need(req.claim_type) and resolved in _IRRELEVANT_FINISH_FOR_NEARBY:
                    continue
                if tool not in pending and resolved not in called:
                    pending.append(tool)
        for tool in contract.entity_policy.preferred_tools:
            resolved = resolve_tool_name(tool)
            if tool not in pending and resolved not in called:
                pending.append(tool)
        return pending
