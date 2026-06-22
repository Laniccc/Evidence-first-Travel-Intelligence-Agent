from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType

_HOURS_PATTERNS = [
    re.compile(r"opening\s*hours?[:\s]+([^<\n]{5,120})", re.I),
    re.compile(r"open(?:ing)?[:\s]+(\d{1,2}[:.]\d{2}\s*[-–]\s*\d{1,2}[:.]\d{2})", re.I),
    re.compile(r"营业时间[：:\s]*([^<\n]{5,80})"),
    re.compile(r"开放时间[：:\s]*([^<\n]{5,80})"),
]
_PRICE_PATTERNS = [
    re.compile(r"(?:admission|ticket|entrance)\s*(?:fee|price)?[:\s]+([^<\n]{3,80})", re.I),
    re.compile(r"(\d{1,3}(?:,\d{3})*\s*(?:yen|円|JPY|CNY|元|RMB))", re.I),
    re.compile(r"门票[：:\s]*([^<\n]{3,60})"),
    re.compile(r"票价[：:\s]*([^<\n]{3,60})"),
]
_RESERVATION_PATTERNS = [
    re.compile(r"(?:reservation|booking)[:\s]+([^<\n]{5,120})", re.I),
    re.compile(r"(预约|予約(?:制|必要)[^<\n]{0,60})", re.I),
]
_CLOSURE_PATTERNS = [
    re.compile(r"(?:temporary\s+)?clos(?:ed|ure)[:\s]+([^<\n]{5,120})", re.I),
    re.compile(r"(临[时時]闭馆|临时闭馆|臨時休業[^<\n]{0,80})", re.I),
]

_OFFICIAL_HOST_HINTS = (".gov", ".gov.cn", ".edu", "tourism", "travel", "景区", "official", "ticket")


def normalize_page_text(raw: str) -> str:
    text = raw
    if "<" in text and ">" in text:
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_first(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def extract_claims_from_text(
    text: str,
    *,
    information_need: str | None = None,
) -> tuple[list[Claim], list[str]]:
    clean = normalize_page_text(text)
    limitations: list[str] = []
    claims: list[Claim] = []
    fields = {
        ClaimType.OPENING_HOURS: _extract_first(_HOURS_PATTERNS, clean),
        ClaimType.TICKET_PRICE: _extract_first(_PRICE_PATTERNS, clean),
        ClaimType.RESERVATION: _extract_first(_RESERVATION_PATTERNS, clean),
        ClaimType.TRAVEL_ADVICE: _extract_first(_CLOSURE_PATTERNS, clean),
    }
    for claim_type, value in fields.items():
        if value:
            claims.append(
                Claim(
                    claim_type=claim_type,
                    value=value,
                    normalized_value={claim_type.value: value},
                    confidence=0.72,
                )
            )
        elif information_need and claim_type.value == information_need:
            limitations.append(f"{claim_type.value} not found in page text")

    if not claims and clean:
        hint = ClaimType.TRAVEL_ADVICE
        if information_need:
            try:
                hint = ClaimType(information_need)
            except ValueError:
                pass
        claims.append(
            Claim(
                claim_type=hint,
                value=clean[:500],
                raw_text=clean[:2000],
                confidence=0.55,
            )
        )
        limitations.append("Structured field extraction failed; stored page excerpt.")
    return claims, limitations


def pick_url_from_evidence(evidence_list: list[Evidence], *, prefer_official: bool = True) -> str | None:
    candidates: list[tuple[int, str]] = []
    for ev in evidence_list:
        url = (ev.source_url or "").strip()
        if not url:
            for claim in ev.claims:
                nv = claim.normalized_value
                if isinstance(nv, str) and nv.startswith("http"):
                    url = nv
                    break
                if isinstance(nv, dict):
                    for v in nv.values():
                        if isinstance(v, str) and v.startswith("http"):
                            url = v
                            break
        if not url:
            continue
        score = 0
        blob = f"{url} {ev.source_name}".lower()
        if prefer_official and any(h in blob for h in _OFFICIAL_HOST_HINTS):
            score += 10
        if ev.source_type == SourceType.OFFICIAL:
            score += 5
        candidates.append((score, url))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def text_from_mcp_payload(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("text", "content", "markdown", "body", "html"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                return val
        if "data" in raw:
            return text_from_mcp_payload(raw["data"])
    if isinstance(raw, list):
        parts = [text_from_mcp_payload(item) for item in raw[:5]]
        return "\n".join(p for p in parts if p)
    return json.dumps(raw, ensure_ascii=False)[:4000]


def build_page_evidence(
    *,
    source_name: str,
    source_url: str | None,
    text: str,
    country: str | None,
    city: str | None,
    place_name: str | None,
    information_need: str | None,
    limitations_extra: list[str] | None = None,
) -> Evidence:
    claims, limitations = extract_claims_from_text(text, information_need=information_need)
    limitations = list(limitations_extra or []) + limitations
    return Evidence(
        source_name=source_name,
        source_type=SourceType.OFFICIAL,
        source_url=source_url,
        country=country or "Unknown",
        city=city,
        place_name=place_name,
        retrieved_at=datetime.utcnow(),
        data_freshness=DataFreshness.RECENT,
        license_scope=LicenseScope.PUBLIC_PAGE,
        confidence=0.75 if any(c.claim_type == ClaimType.TICKET_PRICE for c in claims) else 0.65,
        claims=claims,
        limitations=limitations,
    )
