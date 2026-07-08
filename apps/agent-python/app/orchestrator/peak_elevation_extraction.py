"""Extract peak names and elevation granularity from evidence — no static peak tables."""

from __future__ import annotations

import re

from app.schemas.evidence import Evidence
from app.schemas.peak_elevation import PeakElevationFact, PeakElevationTable

_EXACT_ELEVATION = re.compile(
    r"(?P<peak>[\u4e00-\u9fff]{1,8}峰)?\s*海拔\s*[:：]?\s*(?P<m>\d{3,4}(?:\.\d+)?)\s*米",
    re.I,
)
_PEAK_WITH_ELEVATION = re.compile(
    r"(?P<peak>[\u4e00-\u9fff]{1,8}峰)\s*[^。；\n]{0,24}?(?P<m>\d{3,4}(?:\.\d+)?)\s*米",
)
_RANGE_ONLY = re.compile(
    r"逾\s*\d{3,4}|超过\s*\d{3,4}|约\s*\d{3,4}\s*米\s*以上|均逾\s*\d{3,4}|均在\s*\d{3,4}\s*米",
    re.I,
)
_GENERIC_PEAK_TOKENS = frozenset({"主峰", "山峰", "高峰", "诸峰", "群峰", "顶峰"})
_HIGHEST_HINT = re.compile(r"最高峰|最高峰为|最高点", re.I)
_PEAK_LIST = re.compile(
    r"([\u4e00-\u9fff]{1,6}峰|[\u4e00-\u9fff]{2,4}顶)(?:\s*[,，、]\s*([\u4e00-\u9fff]{1,6}峰|[\u4e00-\u9fff]{2,4}顶))*"
)
_UNRELATED_GEO = re.compile(r"平方千米|经纬度|总面积|南北长约|东西宽约|开放时间|门票", re.I)
_PEAK_TOKEN = re.compile(r"[\u4e00-\u9fff]{1,6}峰|[\u4e00-\u9fff]{2,4}顶")


def classify_elevation_text(text: str) -> str:
    blob = (text or "").strip()
    if not blob:
        return "none"
    if _UNRELATED_GEO.search(blob) and not _EXACT_ELEVATION.search(blob):
        return "unrelated_geo"
    if _RANGE_ONLY.search(blob):
        return "range_only"
    if _EXACT_ELEVATION.search(blob) or _PEAK_WITH_ELEVATION.search(blob):
        return "exact_numeric"
    if re.search(r"海拔", blob) and re.search(r"\d{3,4}", blob):
        return "partial"
    return "none"


def _is_generic_peak_name(name: str) -> bool:
    token = (name or "").strip()
    return not token or token in _GENERIC_PEAK_TOKENS


def _elevation_in_range_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 12) : min(len(text), end + 8)]
    return bool(_RANGE_ONLY.search(window))


def discover_peak_names_from_text(text: str) -> list[str]:
    names: list[str] = []
    for m in _PEAK_TOKEN.finditer(text or ""):
        token = m.group(0).strip()
        if token and token not in names and len(token) >= 2 and not _is_generic_peak_name(token):
            names.append(token)
    return names[:8]


def discover_peak_names_from_evidence(evidence: list) -> list[str]:
    found: list[str] = []
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        parts = [getattr(ev, "place_name", "") or ""]
        for claim in ev.claims or []:
            parts.append(str(getattr(claim, "value", "") or ""))
            parts.append(str(getattr(claim, "raw_text", "") or ""))
        blob = " ".join(parts)
        for name in discover_peak_names_from_text(blob):
            if name not in found:
                found.append(name)
    return found


def extract_peak_elevation_table(
    evidence: list,
    *,
    place_name: str = "",
) -> PeakElevationTable:
    peaks: list[PeakElevationFact] = []
    highest_peak: str | None = None
    granularities: list[str] = []

    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        source = str(getattr(ev, "source_name", "") or "")
        url = getattr(ev, "source_url", None)
        for claim in ev.claims or []:
            text = f"{getattr(claim, 'value', '')} {getattr(claim, 'raw_text', '')}".strip()
            if not text:
                continue
            gran = classify_elevation_text(text)
            granularities.append(gran)
            if gran == "unrelated_geo" or gran == "range_only":
                continue
            if _HIGHEST_HINT.search(text):
                for name in discover_peak_names_from_text(text):
                    if "峰" in name or "顶" in name:
                        highest_peak = highest_peak or name
            for m in _EXACT_ELEVATION.finditer(text):
                peak = (m.group("peak") or "").strip()
                if _is_generic_peak_name(peak):
                    peak = ""
                if _elevation_in_range_context(text, m.start(), m.end()):
                    continue
                try:
                    elev = float(m.group("m"))
                except (TypeError, ValueError):
                    continue
                if not peak:
                    for n in discover_peak_names_from_text(text):
                        peak = n
                        break
                if not peak:
                    continue
                peaks.append(
                    PeakElevationFact(
                        place_name=place_name,
                        peak_name=peak,
                        elevation_m=elev,
                        relation="highest_peak" if _HIGHEST_HINT.search(text) else "main_peak",
                        source_name=source,
                        source_url=url,
                        confidence=float(getattr(claim, "confidence", 0.6) or 0.6),
                        raw_text=text[:240],
                    )
                )
            for m in _PEAK_WITH_ELEVATION.finditer(text):
                peak = m.group("peak").strip()
                if _is_generic_peak_name(peak) or _elevation_in_range_context(text, m.start(), m.end()):
                    continue
                try:
                    elev = float(m.group("m"))
                except (TypeError, ValueError):
                    continue
                if any(p.peak_name == peak and p.elevation_m == elev for p in peaks):
                    continue
                peaks.append(
                    PeakElevationFact(
                        place_name=place_name,
                        peak_name=peak,
                        elevation_m=elev,
                        relation="main_peak",
                        source_name=source,
                        source_url=url,
                        confidence=float(getattr(claim, "confidence", 0.55) or 0.55),
                        raw_text=text[:240],
                    )
                )

    deduped: list[PeakElevationFact] = []
    seen: set[tuple[str, float | None]] = set()
    for p in peaks:
        key = (p.peak_name, p.elevation_m)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    if not highest_peak and deduped:
        ranked = sorted(deduped, key=lambda x: float(x.elevation_m or 0), reverse=True)
        highest_peak = ranked[0].peak_name

    if "exact_numeric" in granularities:
        quality = "strong" if len(deduped) >= 2 else "partial"
        gran = "exact_numeric"
    elif "range_only" in granularities:
        quality = "partial"
        gran = "range_only"
    elif "partial" in granularities:
        quality = "partial"
        gran = "partial"
    else:
        quality = "none"
        gran = "none"

    limitations: list[str] = []
    if gran == "range_only":
        limitations.append("仅有海拔范围描述，缺少各主峰精确米数。")
    if gran == "exact_numeric" and len(deduped) < 2:
        limitations.append("仅查到部分主峰的具体海拔。")

    return PeakElevationTable(
        place_name=place_name,
        highest_peak=highest_peak,
        peaks=deduped,
        coverage_quality=quality,
        value_granularity=gran,
        limitations=limitations,
    )


def elevation_needs_peak_gap(table: PeakElevationTable, *, exact_required: bool = True) -> bool:
    if not exact_required:
        return False
    if table.value_granularity == "exact_numeric" and len(table.peaks) >= 2:
        return False
    if table.value_granularity in {"range_only", "partial", "none"}:
        return True
    return len(table.peaks) < 2
