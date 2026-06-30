"""S3: compile SemanticFrame + query into LookupClaim evidence goals."""

from __future__ import annotations

import re

from app.orchestrator.claim_family_registry import (
    claim_family_for_type,
    extraction_schema_for,
    preferred_source_families_for,
)
from app.orchestrator.lookup_need_aliases import infer_lookup_needs_from_text, is_elevation_lookup_text
from app.orchestrator.ticket_product_policy import extract_ticket_product_context
from app.schemas.intent_profile import IntentProfile, PrimaryIntent
from app.schemas.lookup_claim import LookupClaim
from app.schemas.response_contract import ClaimRequirement
from app.schemas.semantic_frame import SemanticFrame

_OPENING_HOURS_RE = re.compile(r"开放时间|几点开|开馆|闭馆|营业时间|开放吗", re.I)
_TICKET_PRICE_RE = re.compile(r"门票|票价|多少钱|价格|票价多少", re.I)
_SHUTTLE_RE = re.compile(r"区间车|观光车|接驳车|摆渡车", re.I)
_CABLE_RE = re.compile(r"索道|缆车|cable", re.I)
_WINTER_ADVISORY_RE = re.compile(r"冬天|冬季|值得去吗|封路|路况", re.I)
_ROAD_STATUS_RE = re.compile(r"封路|通车|道路开放|能不能去", re.I)


def _target_entity_from_frame(frame: SemanticFrame) -> dict:
    ent = frame.entities
    out: dict = {}
    if ent.places:
        out["place_names"] = list(ent.places)
    if ent.city:
        out["city"] = ent.city
    if ent.country:
        out["country"] = ent.country
    if ent.region:
        out["region"] = ent.region
    return out


def _base_claim(
    claim_type: str,
    *,
    frame: SemanticFrame,
    priority: str = "required",
    requires_exact_fact: bool = False,
    requires_live_data: bool = False,
    model_prior_allowed: bool = False,
    target_scope: str = "whole_place",
    product_or_service: str | None = None,
    product_keywords: list[str] | None = None,
    exclude_products: list[str] | None = None,
    time_scope: str = "unknown",
    claim_description: str | None = None,
) -> LookupClaim:
    family = claim_family_for_type(claim_type)
    return LookupClaim(
        claim_type=claim_type,
        claim_family=family,
        target_entity=_target_entity_from_frame(frame),
        target_scope=target_scope,
        product_or_service=product_or_service,
        product_keywords=list(product_keywords or []),
        exclude_products=list(exclude_products or []),
        time_scope=time_scope,
        requires_exact_fact=requires_exact_fact,
        requires_live_data=requires_live_data,
        model_prior_allowed=model_prior_allowed,
        preferred_source_families=preferred_source_families_for(claim_type),
        extraction_schema=extraction_schema_for(claim_type),
        priority=priority,
        claim_description=claim_description,
    )


def _compile_ticket_claim(text: str, frame: SemanticFrame) -> LookupClaim | None:
    if not _TICKET_PRICE_RE.search(text):
        return None
    product_ctx = extract_ticket_product_context(text)
    if product_ctx and product_ctx.get("ticket_product") == "boat_ticket":
        return _base_claim(
            "boat_ticket_price",
            frame=frame,
            requires_exact_fact=True,
            target_scope="ticket_product",
            product_or_service="boat_ticket",
            product_keywords=list(product_ctx.get("ticket_product_keywords") or []),
            exclude_products=["entrance_ticket", "shuttle_bus_ticket"],
            claim_description="游船/船票价格",
        )
    if _SHUTTLE_RE.search(text):
        return _base_claim(
            "shuttle_bus_ticket_price",
            frame=frame,
            requires_exact_fact=True,
            target_scope="ticket_product",
            product_or_service="shuttle_bus",
            exclude_products=["entrance_ticket", "boat_ticket"],
            claim_description="区间车/观光车票价",
        )
    if _CABLE_RE.search(text):
        return _base_claim(
            "cable_car_ticket_price",
            frame=frame,
            requires_exact_fact=True,
            target_scope="ticket_product",
            product_or_service="cable_car",
            exclude_products=["entrance_ticket", "boat_ticket"],
            claim_description="索道/缆车票价",
        )
    return _base_claim(
        "entrance_ticket_price",
        frame=frame,
        requires_exact_fact=True,
        target_scope="ticket_product",
        product_or_service="entrance_ticket",
        claim_description="景区门票价格",
    )


def _compile_advisory_claims(text: str, frame: SemanticFrame) -> list[LookupClaim]:
    if not _WINTER_ADVISORY_RE.search(text):
        return []
    claims: list[LookupClaim] = []
    if re.search(r"值得|适合|去吗", text):
        claims.append(
            _base_claim(
                "winter_visit_suitability",
                frame=frame,
                priority="important",
                model_prior_allowed=True,
                claim_description="冬季游览适宜性",
            )
        )
    if _ROAD_STATUS_RE.search(text):
        claims.append(
            _base_claim(
                "road_open_status",
                frame=frame,
                requires_exact_fact=True,
                requires_live_data=True,
                model_prior_allowed=False,
                time_scope="current",
                claim_description="道路开放状态",
            )
        )
        claims.append(
            _base_claim(
                "transport_difficulty",
                frame=frame,
                priority="important",
                model_prior_allowed=True,
                claim_description="交通难度",
            )
        )
    if "天气" in text or "下雪" in text:
        claims.append(
            _base_claim(
                "weather_risk",
                frame=frame,
                requires_live_data=True,
                model_prior_allowed=False,
                time_scope="current",
                claim_description="天气风险",
            )
        )
    return claims


def compile_lookup_claims(
    frame: SemanticFrame,
    raw_query: str | None = None,
    *,
    intent_profile: IntentProfile | None = None,
) -> list[LookupClaim]:
    """Compile evidence goals from frame + query text."""
    text = f"{raw_query or ''} {frame.raw_query or ''} {frame.normalized_request or ''}".strip()
    claims: list[LookupClaim] = []

    if _OPENING_HOURS_RE.search(text) or "opening_hours" in (frame.information_needs or []):
        claims.append(
            _base_claim(
                "opening_hours",
                frame=frame,
                requires_exact_fact=True,
                time_scope="stable",
                claim_description="开放时间",
            )
        )

    ticket = _compile_ticket_claim(text, frame)
    if ticket:
        claims.append(ticket)

    if is_elevation_lookup_text(text) or "elevation" in (frame.information_needs or []):
        claim_type = "highest_peak_elevation" if re.search(r"最高|主峰", text) else "elevation"
        claims.append(
            _base_claim(
                claim_type,
                frame=frame,
                requires_exact_fact=True,
                claim_description="海拔/高度",
            )
        )

    for need in infer_lookup_needs_from_text(text):
        if need in {"ticket_price", "opening_hours", "elevation"}:
            continue
        if any(c.claim_type == need for c in claims):
            continue
        claims.append(
            _base_claim(
                need,
                frame=frame,
                requires_exact_fact=need in {"reservation_policy", "temporary_closure"},
                claim_description=need,
            )
        )

    if intent_profile and intent_profile.primary_intent == PrimaryIntent.ADVISORY:
        for adv in _compile_advisory_claims(text, frame):
            if not any(c.claim_type == adv.claim_type for c in claims):
                claims.append(adv)

    if not ticket and "ticket_price" in (frame.information_needs or []):
        claims.append(
            _base_claim(
                "entrance_ticket_price",
                frame=frame,
                requires_exact_fact=True,
                target_scope="ticket_product",
                product_or_service="entrance_ticket",
            )
        )

    return claims


def merge_lookup_claims_into_requirements(
    requirements: list[ClaimRequirement],
    lookup_claims: list[LookupClaim],
) -> list[ClaimRequirement]:
    """Replace/enrich ClaimRequirements with compiled LookupClaims."""
    if not lookup_claims:
        return requirements

    out: list[ClaimRequirement] = []
    replaced_types: set[str] = set()
    lookup_by_type = {lc.claim_type: lc for lc in lookup_claims}

    generic_ticket = lookup_claims[0] if lookup_claims else None
    for lc in lookup_claims:
        if lc.claim_type in {"boat_ticket_price", "entrance_ticket_price", "shuttle_bus_ticket_price"}:
            generic_ticket = lc

    for req in requirements:
        if req.claim_type == "ticket_price" and generic_ticket and generic_ticket.claim_type != "entrance_ticket_price":
            out.append(generic_ticket.to_claim_requirement())
            replaced_types.add("ticket_price")
            replaced_types.add(generic_ticket.claim_type)
            continue
        if req.claim_type in lookup_by_type:
            out.append(lookup_by_type[req.claim_type].to_claim_requirement())
            replaced_types.add(req.claim_type)
            continue
        out.append(req)

    for lc in lookup_claims:
        if lc.claim_type in replaced_types:
            continue
        if any(r.claim_type == lc.claim_type for r in out):
            continue
        out.append(lc.to_claim_requirement())

    return out


def get_lookup_claims_from_state(state) -> list[LookupClaim]:
    structured = getattr(state, "structured_result", None) or {}
    raw = structured.get("lookup_claims") or []
    claims: list[LookupClaim] = []
    for row in raw:
        if isinstance(row, LookupClaim):
            claims.append(row)
        elif isinstance(row, dict):
            claims.append(LookupClaim.model_validate(row))
    if claims:
        return claims
    contract = getattr(state, "response_contract", None)
    if contract and contract.claim_requirements:
        return [LookupClaim.from_claim_requirement(r) for r in contract.claim_requirements]
    return []


def primary_lookup_claim(state) -> LookupClaim | None:
    claims = get_lookup_claims_from_state(state)
    return claims[0] if claims else None
