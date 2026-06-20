import re
from typing import Any

from app.orchestrator.policies import SourcePriorityPolicy
from app.schemas.evidence import ClaimType, Evidence, SourceType
from app.schemas.place_factsheet import FactValue, PlaceFactSheet
from app.catalog.place_catalog import get_place_catalog


FIELD_CLAIM_MAP = {
    "official_hours": ClaimType.OPENING_HOURS,
    "ticket_price": ClaimType.TICKET_PRICE,
    "reservation_policy": ClaimType.RESERVATION,
    "address": ClaimType.ADDRESS,
    "transit_summary": ClaimType.TRANSIT,
    "weather": ClaimType.WEATHER,
    "food_nearby": ClaimType.FOOD,
}

NUMERIC_FIELD_CLAIMS = {
    "crowd_risk": ClaimType.CROWD,
    "accessibility": ClaimType.ACCESSIBILITY,
    "walking_intensity": ClaimType.SAFETY,
    "transport_convenience": ClaimType.TRANSIT,
}


class EvidenceAggregator:
    @staticmethod
    def aggregate(place_name: str, evidence: list[Evidence], conflicts: list | None = None) -> PlaceFactSheet:
        catalog = get_place_catalog()
        canonical = catalog.normalize_place_name(place_name) or place_name
        conflict_fields: set[str] = set()
        for c in conflicts or []:
            field = c.field if hasattr(c, "field") else c.get("field")
            conflict_fields.add(field)
            if field == "opening_hours":
                conflict_fields.add("official_hours")

        ev_by_id = {ev.evidence_id: ev for ev in evidence}
        sheet = PlaceFactSheet(place_name=canonical)
        field_facts: dict[str, FactValue] = {}
        confidences: list[float] = []

        for ev in evidence:
            if ev.country:
                sheet.country = ev.country
            if ev.city:
                sheet.city = ev.city

        for field, claim_type in FIELD_CLAIM_MAP.items():
            text_only = field == "transit_summary"
            value, ev_ids, conf, src_type = EvidenceAggregator._best_text_claim(
                evidence, claim_type, conflict_fields, field, text_only=text_only
            )
            if value is not None:
                setattr(sheet, field, value)
                sheet.source_ids[field] = ev_ids
                field_facts[field] = EvidenceAggregator._fact_value(
                    field, value, ev_ids, conf, ev_by_id, src_type
                )
                confidences.append(conf)

        for field, claim_type in NUMERIC_FIELD_CLAIMS.items():
            if getattr(sheet, field) is not None:
                continue
            num, ev_ids, conf, src_type = EvidenceAggregator._best_numeric_claim(evidence, claim_type)
            if num is not None:
                setattr(sheet, field, num)
                sheet.source_ids[field] = ev_ids
                field_facts[field] = EvidenceAggregator._fact_value(field, num, ev_ids, conf, ev_by_id, src_type)
                confidences.append(conf)

        for ev in evidence:
            for claim in ev.claims:
                if claim.claim_type != ClaimType.REVIEW_ASPECT:
                    continue
                norm = claim.normalized_value
                if isinstance(norm, dict) and norm.get("avg_rating", 0) >= 4.4 and sheet.first_timer_fit is None:
                    val = min(0.95, norm["avg_rating"] / 5.0)
                    sheet.first_timer_fit = val
                    sheet.source_ids["first_timer_fit"] = [ev.evidence_id]
                    field_facts["first_timer_fit"] = EvidenceAggregator._fact_value(
                        "first_timer_fit", val, [ev.evidence_id], claim.confidence, ev_by_id, ev.source_type
                    )
                    confidences.append(claim.confidence)

        sheet.field_facts = field_facts
        sheet.confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
        return sheet

    @staticmethod
    def _fact_value(
        field: str,
        value: Any,
        ev_ids: list[str],
        confidence: float,
        ev_by_id: dict[str, Evidence],
        src_type: SourceType | None,
    ) -> FactValue:
        names, types, limitations = [], [], []
        for eid in ev_ids:
            ev = ev_by_id.get(eid)
            if ev:
                names.append(ev.source_name)
                types.append(ev.source_type.value)
                limitations.extend(ev.limitations)
        if confidence < 0.55:
            limitations.append(f"Low confidence for {field}.")
        return FactValue(
            field=field,
            value=value,
            source_ids=ev_ids,
            source_names=names,
            source_types=types,
            confidence=confidence,
            limitations=list(dict.fromkeys(limitations)),
        )

    @staticmethod
    def _best_text_claim(
        evidence: list[Evidence],
        claim_type: ClaimType,
        conflict_fields: set,
        field_name: str,
        text_only: bool = False,
    ) -> tuple[str | None, list[str], float, SourceType | None]:
        candidates: list[tuple[str, str, float, SourceType]] = []
        for ev in evidence:
            for claim in ev.claims:
                if claim.claim_type != claim_type:
                    continue
                raw = claim.normalized_value if claim.normalized_value is not None else claim.value
                if isinstance(raw, dict) or isinstance(raw, (int, float)):
                    if text_only:
                        continue
                    continue
                text = str(raw).strip()
                if text:
                    candidates.append((text, ev.evidence_id, claim.confidence, ev.source_type))
        if not candidates:
            return None, [], 0.0, None
        candidates.sort(key=lambda c: (SourcePriorityPolicy.rank(c[3]), -c[2]))
        best = candidates[0]
        return best[0], [best[1]], best[2], best[3]

    @staticmethod
    def _best_numeric_claim(
        evidence: list[Evidence],
        claim_type: ClaimType,
    ) -> tuple[float | None, list[str], float, SourceType | None]:
        candidates: list[tuple[float, str, float, SourceType]] = []
        for ev in evidence:
            for claim in ev.claims:
                if claim.claim_type != claim_type:
                    continue
                raw = claim.normalized_value if isinstance(claim.normalized_value, (int, float)) else None
                if raw is None and isinstance(claim.value, (int, float)):
                    raw = float(claim.value)
                if raw is not None:
                    candidates.append((float(raw), ev.evidence_id, claim.confidence, ev.source_type))
        if not candidates:
            return None, [], 0.0, None
        candidates.sort(key=lambda c: (SourcePriorityPolicy.rank(c[3]), -c[2]))
        best = candidates[0]
        return best[0], [best[1]], best[2], best[3]
