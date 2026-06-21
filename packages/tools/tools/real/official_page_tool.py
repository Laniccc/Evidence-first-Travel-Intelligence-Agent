import logging
import re
from datetime import datetime

import httpx

from app.config import get_settings
from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mock_data import normalize_place_name

logger = logging.getLogger(__name__)

_HOURS_PATTERNS = [
    re.compile(r"opening\s*hours?[:\s]+([^<\n]{5,120})", re.I),
    re.compile(r"open(?:ing)?[:\s]+(\d{1,2}[:.]\d{2}\s*[-–]\s*\d{1,2}[:.]\d{2})", re.I),
    re.compile(r"営業時間[：:\s]*([^<\n]{5,80})"),
]
_PRICE_PATTERNS = [
    re.compile(r"(?:admission|ticket|entrance)\s*(?:fee|price)?[:\s]+([^<\n]{3,80})", re.I),
    re.compile(r"(\d{1,3}(?:,\d{3})*\s*(?:yen|円|JPY))", re.I),
]
_RESERVATION_PATTERNS = [
    re.compile(r"(?:reservation|booking)[:\s]+([^<\n]{5,120})", re.I),
    re.compile(r"(予約(?:制|必要)[^<\n]{0,60})", re.I),
]
_CLOSURE_PATTERNS = [
    re.compile(r"(?:temporary\s+)?clos(?:ed|ure)[:\s]+([^<\n]{5,120})", re.I),
    re.compile(r"(臨時休業[^<\n]{0,80})", re.I),
]


def _extract_first(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


class RealOfficialPageTool(BaseTravelTool):
    name = "real_official_page_tool"

    def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.enable_real_official_page)

    def _resolve_url(self, place_name: str) -> str | None:
        settings = get_settings()
        canonical = normalize_place_name(place_name) or place_name
        if canonical in settings.official_page_whitelist:
            return settings.official_page_whitelist[canonical]
        for key, url in settings.official_page_whitelist.items():
            if key.lower() in canonical.lower() or canonical.lower() in key.lower():
                return url
        return None

    async def run(self, place_name: str, **kwargs) -> list[Evidence]:
        settings = get_settings()
        if not self.is_available():
            raise RuntimeError("ENABLE_REAL_OFFICIAL_PAGE=false")

        canonical = normalize_place_name(place_name) or place_name
        url = self._resolve_url(canonical)
        if not url:
            raise RuntimeError(f"No whitelist URL for {canonical}")

        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "EvidenceFirstTravelAgent/0.1 (official-whitelist-pilot)"},
            )
            resp.raise_for_status()
            html = resp.text

        text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)

        limitations: list[str] = []
        claims: list[Claim] = []
        fields = {
            ClaimType.OPENING_HOURS: _extract_first(_HOURS_PATTERNS, text),
            ClaimType.TICKET_PRICE: _extract_first(_PRICE_PATTERNS, text),
            ClaimType.RESERVATION: _extract_first(_RESERVATION_PATTERNS, text),
            ClaimType.TEMPORARY_CLOSURE: _extract_first(_CLOSURE_PATTERNS, text),
        }

        for claim_type, value in fields.items():
            if value:
                claims.append(
                    Claim(
                        claim_type=claim_type,
                        value=value,
                        normalized_value={claim_type.value: value},
                        confidence=0.7,
                    )
                )
            else:
                limitations.append(f"{claim_type.value} could not be reliably extracted from official page")

        if not claims:
            raise RuntimeError("No reliable fields extracted from official page")

        retrieved_at = datetime.utcnow()
        evidence = Evidence(
            source_name="Official Page (whitelist)",
            source_type=SourceType.OFFICIAL,
            source_url=url,
            country=kwargs.get("country") or "",
            city=kwargs.get("city"),
            place_name=canonical,
            retrieved_at=retrieved_at,
            data_freshness=DataFreshness.RECENT,
            license_scope=LicenseScope.PUBLIC_PAGE,
            confidence=0.75,
            claims=claims,
            limitations=limitations,
        )
        return [evidence]
