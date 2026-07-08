from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.ticket_price_text import first_ticket_price_mention, has_explicit_ticket_price_signal

_NAV_HOURS_NOISE = (
    "在线购票",
    "全景故宫",
    "block3",
    "参观须知</a>",
    "展览",
    "志愿服务",
    "故宫讲坛",
)

_HOURS_PATTERNS = [
    re.compile(
        r"开放时间为(\d{1,2}:\d{2}).{0,25}停止入(?:园|馆)时间为(\d{1,2}:\d{2}).{0,25}闭馆时间为(\d{1,2}:\d{2})"
    ),
    re.compile(r"opening\s*hours?[:\s]+([^<\n]{5,120})", re.I),
    re.compile(r"open(?:ing)?[:\s]+(\d{1,2}[:.]\d{2}\s*[-–]\s*\d{1,2}[:.]\d{2})", re.I),
    re.compile(r"营业时间[：:\s]*([^<\n]{5,80})"),
    re.compile(r"开馆时间[为：:\s]*(\d{1,2}:\d{2}[^<\n]{0,60})"),
    re.compile(
        r"(每年)?\s*4月1日[至到-]\s*10月31日[^。]{0,60}(\d{1,2}:\d{2}\s*[—\-–至到]\s*\d{1,2}:\d{2}[^。]{0,60})",
        re.I,
    ),
    re.compile(
        r"(每年)?\s*11月1日[至到-][^。]{0,40}(\d{1,2}:\d{2}\s*[—\-–至到]\s*\d{1,2}:\d{2}[^。]{0,60})",
        re.I,
    ),
    re.compile(r"开放时间[：:\s]*([^<\n]{5,120})"),
    re.compile(r"(\d{1,2}:\d{2}\s*[—\-–至到]\s*\d{1,2}:\d{2}(?:\s*[,，;；].{0,20})?)"),
    re.compile(r"(旺季[^。]{0,30}\d{1,2}:\d{2}[^。]{0,60})"),
    re.compile(r"(淡季[^。]{0,30}\d{1,2}:\d{2}[^。]{0,60})"),
    re.compile(r"(周一[^。]{0,12}闭馆[^。]{0,20})"),
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


def _hours_looks_valid(value: str) -> bool:
    if not value or len(value) < 8:
        return False
    if not re.search(r"\d{1,2}:\d{2}", value):
        return False
    noise = sum(1 for token in _NAV_HOURS_NOISE if token in value)
    if noise >= 2:
        return False
    if len(value) > 180 and noise >= 1:
        return False
    return True


def _hours_match_value(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 3 and match.re.pattern.startswith("开放时间为"):
        return (
            f"开放时间为{match.group(1)}，"
            f"停止入馆时间为{match.group(2)}，"
            f"闭馆时间为{match.group(3)}"
        )
    return (match.group(1) if match.lastindex else match.group(0)).strip()


def _hours_label_kind(label: str) -> str | None:
    text = label.strip().rstrip("：:")
    if "闭馆" in text and "停止" not in text:
        return "close"
    if "停止" in text and ("入馆" in text or "入园" in text):
        return "stop"
    if ("开馆" in text or "开放入馆" in text or "开放" in text) and "停止" not in text:
        return "open"
    return None


def _extract_opening_hours_from_html(raw: str) -> str | None:
    announcement = re.search(
        r"开放时间为(\d{1,2}:\d{2}).{0,25}停止入(?:园|馆)时间为(\d{1,2}:\d{2}).{0,25}闭馆时间为(\d{1,2}:\d{2})",
        raw,
    )
    if announcement:
        value = _hours_match_value(announcement)
        if _hours_looks_valid(value):
            return value

    seasons: list[str] = []
    season_re = re.compile(
        r"(\d{1,2}月\d{1,2}日(?:至|到)(?:(?:次|来)年)?\d{1,2}月\d{1,2}日[^<]{0,48})",
    )
    li_re = re.compile(r'<div class="li">([^<]+)<span>(\d{1,2}:\d{2})</span>')
    for season_match in season_re.finditer(raw):
        block = raw[season_match.start() : season_match.start() + 900]
        times: dict[str, str] = {}
        for li_match in li_re.finditer(block):
            label = li_match.group(1)
            if "珍宝" in label or "钟表" in label:
                continue
            kind = _hours_label_kind(label)
            if kind and kind not in times:
                times[kind] = li_match.group(2)
        if not times.get("open"):
            continue
        season_title = normalize_page_text(season_match.group(1))
        parts = [f"{season_title}: 开馆{times['open']}"]
        if times.get("stop"):
            parts.append(f"停止入馆{times['stop']}")
        if times.get("close"):
            parts.append(f"闭馆{times['close']}")
        seasons.append("，".join(parts))

    if seasons:
        result = "；".join(seasons)
        monday = re.search(r"周一[^<\n]{0,16}闭馆", raw)
        if monday:
            result += "；" + normalize_page_text(monday.group(0))
        if _hours_looks_valid(result):
            return result
    return None


def _score_hours_candidate(value: str) -> int:
    score = 0
    if re.search(r"\d{1,2}:\d{2}", value):
        score += 5
    if "4月" in value or "10月" in value or "11月" in value:
        score += 3
    if "开馆" in value:
        score += 2
    if "闭馆" in value:
        score += 1
    if "周一" in value:
        score += 1
    score -= len(value) // 40
    score -= sum(3 for token in _NAV_HOURS_NOISE if token in value)
    return score


def _extract_opening_hours(raw: str, clean: str) -> str | None:
    if "<" in raw:
        from_html = _extract_opening_hours_from_html(raw)
        if from_html:
            return from_html

    candidates: list[str] = []
    for pattern in _HOURS_PATTERNS:
        for match in pattern.finditer(raw if "<" in raw else clean):
            value = _hours_match_value(match)
            if _hours_looks_valid(value):
                candidates.append(value)
    if not candidates:
        return None
    candidates.sort(key=_score_hours_candidate, reverse=True)
    return candidates[0]


def _extract_first(patterns: list[re.Pattern[str]], text: str) -> str | None:
    best: str | None = None
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        value = (match.group(1) if match.lastindex else match.group(0)).strip()
        if len(value) > len(best or ""):
            best = value
    return best


def extract_claims_from_text(
    text: str,
    *,
    information_need: str | None = None,
) -> tuple[list[Claim], list[str]]:
    clean = normalize_page_text(text)
    limitations: list[str] = []
    claims: list[Claim] = []
    focused = None
    if information_need:
        try:
            focused = ClaimType(information_need)
        except ValueError:
            focused = None

    field_extractors = {
        ClaimType.OPENING_HOURS: lambda: _extract_opening_hours(text, clean),
        ClaimType.TICKET_PRICE: lambda: first_ticket_price_mention(clean),
        ClaimType.RESERVATION: lambda: _extract_first(_RESERVATION_PATTERNS, clean),
        ClaimType.TRAVEL_ADVICE: lambda: _extract_first(_CLOSURE_PATTERNS, clean),
    }
    if focused and focused in field_extractors:
        targets = [focused]
    else:
        targets = list(field_extractors.keys())

    fields = {claim_type: field_extractors[claim_type]() for claim_type in targets}
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
        claims.append(
            Claim(
                claim_type=ClaimType.TRAVEL_ADVICE,
                value=clean[:500],
                raw_text=clean[:2000],
                confidence=0.55,
            )
        )
        limitations.append("Structured field extraction failed; stored page excerpt.")
    return claims, limitations


def pick_url_from_evidence(evidence_list: list[Evidence], *, prefer_official: bool = True) -> str | None:
    from tools.official_source.url_normalizer import is_official_reader_url, is_redirect_wrapper_url, is_readable_page_url

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
                    cand_url = nv.get("url")
                    if isinstance(cand_url, str) and cand_url.startswith("http"):
                        url = cand_url
                        break
                    for v in nv.values():
                        if isinstance(v, str) and v.startswith("http"):
                            url = v
                            break
        if not url or is_redirect_wrapper_url(url) or not is_readable_page_url(url):
            continue
        if prefer_official and not is_official_reader_url(url):
            continue
        score = 0
        blob = f"{url} {ev.source_name}".lower()
        if prefer_official and any(h in blob for h in _OFFICIAL_HOST_HINTS):
            score += 10
        if ev.source_type == SourceType.OFFICIAL:
            score += 5
        if "official source discovery" in (ev.source_name or "").lower():
            score += 8
        score += 3
        candidates.append((score, url))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def text_from_mcp_payload(raw: Any) -> str:
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                return text_from_mcp_payload(json.loads(stripped))
            except json.JSONDecodeError:
                pass
        return raw
    if isinstance(raw, dict):
        if raw.get("truncated") and isinstance(raw.get("preview"), str):
            preview = raw["preview"]
            try:
                return text_from_mcp_payload(json.loads(preview))
            except json.JSONDecodeError:
                content_match = re.search(
                    r'"content"\s*:\s*"(?P<body>(?:\\.|[^"\\])*)"',
                    preview,
                )
                if content_match:
                    try:
                        return json.loads(f'"{content_match.group("body")}"')
                    except json.JSONDecodeError:
                        return content_match.group("body")
                return preview
        for key in ("content", "html", "text", "markdown", "body"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                return val
        if "data" in raw:
            return text_from_mcp_payload(raw["data"])
    if isinstance(raw, list):
        parts = [text_from_mcp_payload(item) for item in raw[:5]]
        return "\n".join(p for p in parts if p)
    return json.dumps(raw, ensure_ascii=False)[:4000]


def claim_substantively_satisfies_need(claim: Claim, information_need: str | None) -> bool:
    if not information_need:
        return True
    try:
        target = ClaimType(information_need)
    except ValueError:
        from tools.official_source.official_page_follower import _NEED_TO_CLAIM

        target = _NEED_TO_CLAIM.get(information_need)
        if not target:
            return float(claim.confidence or 0) >= 0.65
    ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
    if ct != target.value:
        return False
    if float(claim.confidence or 0) < 0.65:
        return False
    value = str(claim.value or "")
    if target == ClaimType.OPENING_HOURS:
        return _hours_looks_valid(value)
    if target == ClaimType.TICKET_PRICE:
        return has_explicit_ticket_price_signal(value)
    return len(value.strip()) >= 8


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
        confidence=(
            0.85
            if any(
                c.claim_type == ClaimType.OPENING_HOURS
                and _hours_looks_valid(str(c.value))
                for c in claims
            )
            else 0.75
            if any(c.claim_type == ClaimType.TICKET_PRICE for c in claims)
            else 0.65
        ),
        claims=claims,
        limitations=limitations,
    )
