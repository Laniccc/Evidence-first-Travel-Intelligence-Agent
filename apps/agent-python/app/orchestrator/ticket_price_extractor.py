"""Extract structured TicketPriceFact from evidence."""

from __future__ import annotations

from app.orchestrator.claim_family_registry import claim_family_for_type
from app.orchestrator.evidence_ladder import strength_for_evidence
from app.schemas.claim_facts import TicketPriceFact
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.lookup_claim import LookupClaim
from tools.ticket_price_text import first_ticket_price_amount, has_explicit_ticket_price_signal
from app.orchestrator.ticket_price_audit import is_platform_addon_for_claim

_PRODUCT_INCLUDE_HINTS = {
    "boat_ticket": ("游船", "船票", "游船票", "码头", "双湖游船"),
    "shuttle_bus": ("区间车", "观光车", "景交车", "交通车"),
    "cable_car": ("索道", "缆车", "索道票", "缆车票"),
}

_PRODUCT_EXCLUDE_HINTS = {
    "entrance_ticket": ("游船", "船票", "区间车", "观光车", "景交车", "索道", "缆车"),
    "boat_ticket": ("大门票", "入园票", "区间车", "观光车", "景交车", "索道", "缆车"),
    "shuttle_bus": ("大门票", "入园票", "游船", "船票", "索道", "缆车"),
    "cable_car": ("大门票", "入园票", "游船", "船票", "区间车", "观光车", "景交车"),
}

_AREA_FREE_POLICY_HINTS = (
    "开放区域",
    "公共区域",
    "步行街",
    "街区",
    "风光带",
    "主街区",
)

_ENTRANCE_INCLUDE_HINTS = (
    "大门票",
    "门票",
    "入园票",
    "入馆票",
    "成人票",
    "admission",
    "entrance",
)

_ADDON_OR_SPOT_HINTS = (
    "珍宝馆",
    "钟表馆",
    "展览",
    "特展",
    "讲解",
    "导览",
    "午门",
    "神武门",
    "御花园",
    "角楼",
    "太和殿",
    "慈宁宫",
)


def _product_from_claim(claim: LookupClaim | None, claim_type: str) -> str:
    if claim and claim.product_or_service:
        return claim.product_or_service
    if claim_type == "boat_ticket_price":
        return "boat_ticket"
    if claim_type == "shuttle_bus_ticket_price":
        return "shuttle_bus"
    if claim_type == "cable_car_ticket_price":
        return "cable_car"
    return "entrance_ticket"


def _blob_matches_product(blob: str, product: str, exclude_products: list[str]) -> bool:
    for ex in exclude_products:
        hints = _PRODUCT_INCLUDE_HINTS.get(ex, ()) or _PRODUCT_EXCLUDE_HINTS.get(ex, ())
        if any(h in blob for h in hints):
            return False
    exclude_hints = _PRODUCT_EXCLUDE_HINTS.get(product, ())
    if product == "entrance_ticket":
        return not any(h in blob for h in exclude_hints)
    if any(h in blob for h in exclude_hints):
        return False
    include_hints = _PRODUCT_INCLUDE_HINTS.get(product, ())
    return any(h in blob for h in include_hints) or product.replace("_", "") in blob.lower()


def _looks_like_entrance_ticket(blob: str) -> bool:
    if any(h in blob for h in _ADDON_OR_SPOT_HINTS):
        return False
    return any(h in blob for h in _ENTRANCE_INCLUDE_HINTS)


def extract_ticket_price_from_text(
    text: str,
    *,
    claim_type: str = "ticket_price",
    claim: LookupClaim | None = None,
    source_url: str | None = None,
    source_class: str = "unknown",
    evidence_strength: str = "partial",
) -> TicketPriceFact | None:
    blob = str(text or "").strip()
    if len(blob) < 3:
        return None
    product = _product_from_claim(claim, claim_type)
    exclude = list(claim.exclude_products if claim else [])
    if not _blob_matches_product(blob, product, exclude):
        return None
    if not has_explicit_ticket_price_signal(blob):
        return None
    adult_price = first_ticket_price_amount(blob)
    if adult_price is None:
        return None
    if source_class in {"ticket_platform", "platform"}:
        if is_platform_addon_for_claim(blob, claim_type=claim_type):
            return None
    return TicketPriceFact(
        ticket_product=product,
        ticket_name=claim.claim_description if claim else None,
        adult_price=adult_price,
        source_class=source_class,
        source_url=source_url,
        evidence_strength=evidence_strength,
        raw_text=blob[:200],
    )


def extract_ticket_price_from_evidence(
    evidence: list,
    *,
    claim: LookupClaim | None = None,
    claim_type: str | None = None,
) -> list[TicketPriceFact]:
    ct = claim_type or (claim.claim_type if claim else "ticket_price")
    family = claim_family_for_type(ct)
    out: list[TicketPriceFact] = []
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        strength = strength_for_evidence(ev, family)
        if strength in {"rejected", "no_evidence"}:
            continue
        from app.orchestrator.search_snippet_policy import _source_type_label

        parts = [str(ev.source_name or ""), str(ev.source_url or "")]
        ticket_name: str | None = None
        booking_url: str | None = ev.source_url
        product_title: str | None = None
        has_structured_ticket_claim = False
        for c in ev.claims or []:
            ctype = c.claim_type.value if hasattr(c.claim_type, "value") else str(c.claim_type)
            if ctype in {
                ClaimType.TICKET_PRICE.value,
                ClaimType.TICKET_PRICE_CANDIDATE.value,
                ClaimType.PRICE_CANDIDATE.value,
                ClaimType.ACTIVITY_PRICE.value,
                ClaimType.TICKET_TYPE.value,
            }:
                has_structured_ticket_claim = True
            if ctype in {
                ClaimType.TICKET_PRICE.value,
                ClaimType.TICKET_PRICE_CANDIDATE.value,
                ClaimType.PRICE_CANDIDATE.value,
            } or any(ch.isdigit() for ch in str(c.value or "")):
                parts.append(str(c.value or ""))
            if ctype == ClaimType.ACTIVITY_PRICE.value and c.value:
                product_title = str(c.value).strip()
                parts.append(product_title)
            if ctype == ClaimType.TICKET_TYPE.value and c.value:
                ticket_name = str(c.value).strip()
                parts.append(ticket_name)
            if ctype == ClaimType.PLATFORM_TICKET_URL.value and c.value:
                booking_url = str(c.value).strip()
        source_class = _source_type_label(ev.source_type)
        blob_for_policy = " ".join(parts)
        if (
            source_class in {"web", "search_snippet"}
            and any(h in blob_for_policy for h in _AREA_FREE_POLICY_HINTS)
            and any(h in blob_for_policy for h in ("免费开放", "无需门票", "不需要门票", "免门票"))
        ):
            continue
        if source_class in {"ticket_platform", "platform"} and not has_structured_ticket_claim:
            continue
        fact = extract_ticket_price_from_text(
            " ".join(parts),
            claim_type=ct,
            claim=claim,
            source_url=ev.source_url,
            source_class=source_class,
            evidence_strength=strength,
        )
        if fact:
            if product_title and ticket_name and product_title in ticket_name:
                fact.ticket_name = ticket_name
            elif product_title and ticket_name and ticket_name not in product_title:
                fact.ticket_name = f"{product_title} - {ticket_name}"
            elif product_title:
                fact.ticket_name = product_title
            elif ticket_name:
                fact.ticket_name = ticket_name
            if booking_url:
                fact.booking_url = booking_url
            out.append(fact)
    return out
