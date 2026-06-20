from app.orchestrator.policies import SourcePriorityPolicy
from app.schemas.evidence import ClaimType, Evidence, SourceType
from app.schemas.place_factsheet import PlaceFactSheet
from app.tools.mock_data import normalize_place_name


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
        canonical = normalize_place_name(place_name) or place_name
        conflict_fields: set[str] = set()
        for c in conflicts or []:
            field = c.field if hasattr(c, "field") else c.get("field")
            conflict_fields.add(field)
            if field == "opening_hours":
                conflict_fields.add("official_hours")

        sheet = PlaceFactSheet(place_name=canonical)
        for ev in evidence:
            if ev.country:
                sheet.country = ev.country
            if ev.city:
                sheet.city = ev.city

        source_ids: dict[str, list[str]] = {}
        confidences: list[float] = []

        for field, claim_type in FIELD_CLAIM_MAP.items():
            if field == "transit_summary":
                value, ev_ids, conf = EvidenceAggregator._best_text_claim(evidence, claim_type, conflict_fields, field, text_only=True)
            else:
                value, ev_ids, conf = EvidenceAggregator._best_text_claim(evidence, claim_type, conflict_fields, field)
            if value is not None:
                setattr(sheet, field, value)
                source_ids[field] = ev_ids
                confidences.append(conf)

        for field, claim_type in NUMERIC_FIELD_CLAIMS.items():
            if getattr(sheet, field) is not None:
                continue
            num, ev_ids, conf = EvidenceAggregator._best_numeric_claim(evidence, claim_type, field)
            if num is not None:
                setattr(sheet, field, num)
                source_ids[field] = ev_ids
                confidences.append(conf)

        for ev in evidence:
            for claim in ev.claims:
                if claim.claim_type != ClaimType.REVIEW_ASPECT:
                    continue
                norm = claim.normalized_value
                if isinstance(norm, dict) and norm.get("avg_rating", 0) >= 4.4 and sheet.first_timer_fit is None:
                    sheet.first_timer_fit = min(0.95, norm["avg_rating"] / 5.0)
                    source_ids["first_timer_fit"] = [ev.evidence_id]
                    confidences.append(claim.confidence)

        sheet.source_ids = source_ids
        sheet.confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
        return sheet

    @staticmethod
    def _best_text_claim(
        evidence: list[Evidence],
        claim_type: ClaimType,
        conflict_fields: set,
        field_name: str,
        text_only: bool = False,
    ) -> tuple[str | None, list[str], float]:
        candidates: list[tuple[str, str, float, SourceType]] = []
        for ev in evidence:
            for claim in ev.claims:
                if claim.claim_type != claim_type:
                    continue
                raw = claim.normalized_value if claim.normalized_value is not None else claim.value
                if isinstance(raw, dict):
                    if text_only:
                        continue
                    continue
                if isinstance(raw, (int, float)):
                    if text_only:
                        continue
                    continue
                text = str(raw).strip()
                if text:
                    candidates.append((text, ev.evidence_id, claim.confidence, ev.source_type))

        if not candidates:
            return None, [], 0.0

        if field_name in conflict_fields or field_name.replace("_policy", "") in conflict_fields:
            candidates.sort(key=lambda c: (SourcePriorityPolicy.rank(c[3]), -c[2]))
        else:
            candidates.sort(key=lambda c: (SourcePriorityPolicy.rank(c[3]), -c[2]))

        best = candidates[0]
        return best[0], [best[1]], best[2]

    @staticmethod
    def _best_numeric_claim(
        evidence: list[Evidence],
        claim_type: ClaimType,
        field_name: str,
    ) -> tuple[float | None, list[str], float]:
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
            return None, [], 0.0
        candidates.sort(key=lambda c: (SourcePriorityPolicy.rank(c[3]), -c[2]))
        best = candidates[0]
        return best[0], [best[1]], best[2]
