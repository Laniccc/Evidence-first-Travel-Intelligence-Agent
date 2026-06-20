from app.schemas.evidence import ClaimType, Evidence, SourceType
from app.schemas.review import PersonaImplication, ReviewAspect, ReviewAspectName, ReviewAspectResult, ReviewInputItem
from app.schemas.user_query import UserGoal
from app.tools import ToolRegistry


ASPECT_KEYWORDS = {
    ReviewAspectName.CROWD_LEVEL: ["crowd", " crowded", "人多", "密集", "旅行团"],
    ReviewAspectName.QUEUE_TIME: ["queue", "line", "排队"],
    ReviewAspectName.PHOTO_EXPERIENCE: ["photo", "拍照", "view", "景"],
    ReviewAspectName.ELDERLY_FRIENDLINESS: ["elderly", "senior", "老人", "父母", "rest", "坡"],
    ReviewAspectName.WALKING_INTENSITY: ["walk", "hike", "uphill", "steep", "坡", "走"],
    ReviewAspectName.ACCESSIBILITY: ["wheelchair", "mobility", "无障碍"],
    ReviewAspectName.TRANSPORT_CONVENIENCE: ["metro", "bus", "station", "地铁", "交通"],
    ReviewAspectName.FIRST_TIMER_FIT: ["must-see", "iconic", "first", "经典", "第一次"],
    ReviewAspectName.OVERRATED_RISK: ["overrated", "名不副实"],
}


class ReviewAspectMiningAgent:
    REQUIRED_ASPECTS = list(ReviewAspectName)

    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    async def run(self, place_name: str, goal: UserGoal) -> ReviewAspectResult:
        raw = self.tools.reviews.get_raw_reviews(place_name)
        reviews = [ReviewInputItem(**r) for r in raw]
        profile = {"party": [p.value for p in goal.party], "pace": goal.pace.value, "preferences": goal.preferences}
        result = self._mine(place_name, reviews, profile)
        return result

    def _mine(self, place_name: str, reviews: list[ReviewInputItem], profile: dict) -> ReviewAspectResult:
        aspects: list[ReviewAspect] = []
        combined = " ".join(r.text.lower() for r in reviews)
        for aspect, keywords in ASPECT_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in combined)
            if hits == 0:
                continue
            sentiment = "negative" if aspect in {ReviewAspectName.CROWD_LEVEL, ReviewAspectName.WALKING_INTENSITY, ReviewAspectName.QUEUE_TIME} else "positive"
            aspects.append(
                ReviewAspect(
                    aspect=aspect,
                    sentiment=sentiment,
                    frequency=min(1.0, hits / max(len(reviews), 1)),
                    recent_trend="stable",
                    evidence_examples=[r.text[:120] for r in reviews[:2]],
                    confidence=0.7,
                )
            )
        persona_implications = self._persona_fit(aspects, profile)
        summary = f"Based on {len(reviews)} recent review summaries for {place_name}."
        return ReviewAspectResult(
            place_name=place_name,
            review_summary=summary,
            aspects=aspects,
            persona_implications=persona_implications,
            limitations=["Review mining uses summaries only in MVP."],
        )

    def _persona_fit(self, aspects: list[ReviewAspect], profile: dict) -> list[PersonaImplication]:
        implications: list[PersonaImplication] = []
        party = profile.get("party", [])
        if "elderly" in party:
            walk = next((a for a in aspects if a.aspect == ReviewAspectName.WALKING_INTENSITY), None)
            crowd = next((a for a in aspects if a.aspect == ReviewAspectName.CROWD_LEVEL), None)
            fit = "moderate"
            reason = "Cultural value is high but slopes/crowds may be challenging."
            if walk and walk.sentiment == "negative":
                fit = "moderate" if crowd else "poor"
                reason = "Reviews and profile indicate uphill walking and fatigue risk for seniors."
            implications.append(PersonaImplication(persona="elderly", fit=fit, reason=reason))
        if "couple" in party:
            implications.append(PersonaImplication(persona="couple", fit="good", reason="Scenic and photogenic, best at quieter hours."))
        if not party and "第一次" not in str(profile):
            implications.append(PersonaImplication(persona="first_timer", fit="good", reason="Strong cultural landmark value."))
        return implications


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
            winner = None
            from app.orchestrator.policies import SourceSelectionPolicy

            winner = SourceSelectionPolicy.resolve_conflict_winners(evidence, "opening_hours")
            conflicts.append(
                {
                    "field": "opening_hours",
                    "description": "Multiple opening hour values detected across sources.",
                    "sources": [s for group in hours.values() for s in group],
                    "resolution": f"Prefer official source when available ({winner or 'official priority'}).",
                }
            )
        if len(prices) > 1:
            from app.orchestrator.policies import SourceSelectionPolicy

            winner = SourceSelectionPolicy.resolve_conflict_winners(evidence, "ticket_price")
            conflicts.append(
                {
                    "field": "ticket_price",
                    "description": "Ticket price differs across sources.",
                    "sources": [s for group in prices.values() for s in group],
                    "resolution": f"Prefer official source when available ({winner or 'official priority'}).",
                }
            )
        return conflicts
