from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from tools.base import BaseTravelTool


class MockFallbackTool(BaseTravelTool):
    name = "fallback"

    async def run(self, **kwargs) -> list[Evidence]:
        place_name = kwargs.get("place_name", "unknown")
        need_types = kwargs.get("need_types") or []
        country = kwargs.get("country")
        city = kwargs.get("city")
        tool_limitations = [
            "Fallback source: not a live API.",
            "Crowd/queue figures are estimates only.",
        ]
        if not country or not city:
            tool_limitations.append("Location unknown for fallback estimate.")
        claims = [
            Claim(
                claim_type=ClaimType.REVIEW_ASPECT,
                value="fallback_estimate",
                normalized_value="fallback_estimate",
                confidence=0.35,
                metadata={"disclaimer": "No direct live data source; estimate only."},
            ),
        ]
        if "crowd_level" in need_types or not need_types:
            claims.append(
                Claim(
                    claim_type=ClaimType.CROWD,
                    value=0.65,
                    normalized_value=0.65,
                    confidence=0.4,
                    metadata={"source": "fallback_proxy", "note": "Estimated from reviews/popularity proxy, not live crowd data."},
                )
            )
        if "event" in need_types:
            claims.append(
                Claim(
                    claim_type=ClaimType.SAFETY,
                    value="No verified event data in MVP fallback.",
                    normalized_value="unknown_event",
                    confidence=0.3,
                )
            )
        return [
            Evidence(
                source_name="Fallback Web Lookup (Mock)",
                source_type=SourceType.WEB,
                source_url="https://mock-fallback.local/",
                country=country,
                city=city,
                place_name=place_name,
                confidence=0.35,
                claims=claims,
                limitations=tool_limitations,
            )
        ]
