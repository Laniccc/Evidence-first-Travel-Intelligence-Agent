"""Generic opening-hours structure extraction from arbitrary evidence text."""

from __future__ import annotations

import re

from app.schemas.claim_facts import OpeningHoursFact

_OPEN_TIME = re.compile(
    r"(?:开放|开馆|入馆|开始售票|售票时间|开放入馆)[：:为]?\s*(\d{1,2}[:：]\d{2})",
    re.I,
)
_LAST_TICKET = re.compile(r"(?:止票|停止售票|售票截止)[：:为]?\s*(\d{1,2}[:：]\d{2})", re.I)
_LAST_ENTRY = re.compile(r"(?:停止入馆|止入馆|最后入馆)[：:为]?\s*(\d{1,2}[:：]\d{2})", re.I)
_CLOSE_TIME = re.compile(r"(?:闭馆|清场|关门)[：:为]?\s*(\d{1,2}[:：]\d{2})", re.I)
_CLOSED_DAYS = re.compile(r"(周[一二三四五六日天]|星期[一二三四五六日天])[休闭馆停]?", re.I)
_SEASON_RANGE = re.compile(
    r"(\d{1,2}月\d{1,2}日?\s*[-–—至到]\s*\d{1,2}月\d{1,2}日?)",
    re.I,
)
_TIME_TOKEN = re.compile(r"\b(\d{1,2}[:：]\d{2})\b")


def _norm_time(token: str) -> str:
    return token.replace("：", ":").strip()


def extract_opening_hours_from_text(
    text: str,
    *,
    source_url: str | None = None,
    source_class: str = "unknown",
    evidence_strength: str = "partial",
) -> OpeningHoursFact | None:
    blob = str(text or "").strip()
    if len(blob) < 4:
        return None
    fact = OpeningHoursFact(
        source_url=source_url,
        source_class=source_class,
        evidence_strength=evidence_strength,
    )
    if m := _OPEN_TIME.search(blob):
        fact.open_time = _norm_time(m.group(1))
    if m := _LAST_TICKET.search(blob):
        fact.last_ticket_time = _norm_time(m.group(1))
    if m := _LAST_ENTRY.search(blob):
        fact.last_entry_time = _norm_time(m.group(1))
    if m := _CLOSE_TIME.search(blob):
        fact.close_time = _norm_time(m.group(1))
    for m in _CLOSED_DAYS.finditer(blob):
        day = m.group(1)
        if day and day not in fact.closed_days:
            fact.closed_days.append(day)
    if m := _SEASON_RANGE.search(blob):
        fact.date_range = m.group(1).strip()
    if not fact.open_time and not fact.close_time:
        times = [_norm_time(t) for t in _TIME_TOKEN.findall(blob)]
        if len(times) >= 2:
            fact.open_time = times[0]
            fact.close_time = times[-1]
        elif len(times) == 1:
            fact.open_time = times[0]
    if not fact.summary_line():
        return None
    return fact


def extract_opening_hours_from_evidence(evidence) -> list[OpeningHoursFact]:
    from app.schemas.evidence import Evidence

    out: list[OpeningHoursFact] = []
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        from app.orchestrator.search_snippet_policy import _source_type_label, evidence_strength_for_claim

        strength = evidence_strength_for_claim(ev, "opening_hours")
        blob_parts = [str(ev.source_name or ""), str(ev.source_url or "")]
        for claim in ev.claims or []:
            blob_parts.append(str(claim.value or ""))
        fact = extract_opening_hours_from_text(
            " ".join(blob_parts),
            source_url=ev.source_url,
            source_class=_source_type_label(ev.source_type),
            evidence_strength=strength,
        )
        if fact:
            out.append(fact)
    return out
