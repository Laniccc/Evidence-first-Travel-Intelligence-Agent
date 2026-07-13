import importlib
from typing import Any

from app.evidence.evidence_model import ClaimType, Evidence, SourceType
from app.evidence.review import ReviewAspectResult, ReviewInputItem
from app.evidence.source_priority_policy import SourcePriorityPolicy


def _module(name: str):
    return importlib.import_module(name)


def _resolve_conflict_winner(evidence: list[Evidence], claim_type: ClaimType) -> str | None:
    best_source = None
    best_rank = 999
    for evidence_item in evidence:
        if not isinstance(evidence_item, Evidence):
            continue
        for claim in evidence_item.claims:
            if claim.claim_type != claim_type:
                continue
            rank = SourcePriorityPolicy.rank(evidence_item.source_type)
            if rank < best_rank:
                best_rank = rank
                best_source = evidence_item.source_name
    return best_source


class ReviewAspectMiningAgent:
    def __init__(self, tools: Any) -> None:
        self.tools = tools
        self.rule_extractor = _module("app.evidence.review_rule_extractor").RuleReviewAspectExtractor()
        self.llm_extractor = _module("app.evidence.review_llm_extractor").LLMReviewAspectExtractor()
        self.normalizer = _module("app.evidence.review_aspect_normalizer").AspectNormalizer()
        self.persona_generator = _module("app.evidence.review_persona_generator").PersonaImplicationGenerator()

    async def run(self, place_name: str, goal: Any) -> ReviewAspectResult:
        raw = self.tools.reviews.get_raw_reviews(place_name)
        reviews = [ReviewInputItem(**r) for r in raw]
        profile = {"party": [p.value for p in goal.party], "pace": goal.pace.value, "preferences": goal.preferences}
        aspects = self.rule_extractor.extract(reviews)
        llm_aspects = await self.llm_extractor.extract(reviews)
        aspects = self.normalizer.normalize(aspects + llm_aspects)
        persona_implications = self.persona_generator.generate(aspects, profile)
        return ReviewAspectResult(
            place_name=place_name,
            review_summary=f"Based on {len(reviews)} recent review summaries for {place_name}.",
            aspects=aspects,
            persona_implications=persona_implications,
            limitations=["Review mining uses summaries only in MVP."],
        )


class VerifierAgent:
    @staticmethod
    def validate(evidence: list[Evidence]) -> list[str]:
        issues: list[str] = []
        for ev in evidence:
            if not ev.source_url and ev.source_type not in {SourceType.WEATHER_API, SourceType.TRANSIT_API}:
                issues.append(f"Missing source URL for {ev.source_name}")
            if ev.confidence < 0.35:
                issues.append(f"Low confidence evidence from {ev.source_name}")
            if not ev.claims:
                issues.append(f"No claims in evidence from {ev.source_name}")
        return issues

    @staticmethod
    def normalize(evidence: list[Evidence]) -> list[Evidence]:
        return evidence

    @staticmethod
    def detect_conflicts(evidence: list[Evidence]) -> list[dict]:
        hours = {}
        prices = {}
        conflicts = []
        for ev in evidence:
            for claim in ev.claims:
                if claim.claim_type == ClaimType.OPENING_HOURS:
                    hours.setdefault(str(claim.normalized_value or claim.value), []).append(ev.source_name)
                if claim.claim_type == ClaimType.TICKET_PRICE:
                    prices.setdefault(str(claim.normalized_value or claim.value), []).append(ev.source_name)
        if len(hours) > 1:
            winner = _resolve_conflict_winner(evidence, ClaimType.OPENING_HOURS)
            conflicts.append(
                {
                    "field": "opening_hours",
                    "description": "Multiple opening hour values detected across sources.",
                    "sources": [s for group in hours.values() for s in group],
                    "resolution": f"Prefer official source when available ({winner or 'official priority'}).",
                }
            )
        if len(prices) > 1:
            winner = _resolve_conflict_winner(evidence, ClaimType.TICKET_PRICE)
            conflicts.append(
                {
                    "field": "ticket_price",
                    "description": "Ticket price differs across sources.",
                    "sources": [s for group in prices.values() for s in group],
                    "resolution": f"Prefer official source when available ({winner or 'official priority'}).",
                }
            )

        signal_utils = _module("app.evidence.evidence_signal_utils")
        distance_km_values = signal_utils.distance_km_values
        distance_values_conflict = signal_utils.distance_values_conflict
        visit_duration_buckets = signal_utils.visit_duration_buckets

        duration_buckets = visit_duration_buckets(evidence)
        if len(duration_buckets) >= 2:
            conflicts.append(
                {
                    "field": "visit_duration",
                    "description": (
                        "Visit duration suggestions conflict (e.g. hours inside scenic area vs multi-day stay)."
                    ),
                    "sources": [],
                    "resolution": "Decompose by scope: in-park half-day vs multi-day itinerary.",
                }
            )
        if distance_values_conflict(evidence):
            kms = sorted(distance_km_values(evidence))
            conflicts.append(
                {
                    "field": "distance",
                    "description": f"Distance values differ across sources (km samples: {kms[:6]}).",
                    "sources": [],
                    "resolution": "Label origin/destination; prefer route API over unverified snippets.",
                }
            )
        return conflicts
