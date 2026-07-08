"""Area-level ticket policy helpers for open scenic districts and paid sub-items."""

from __future__ import annotations

import re
from typing import Any

from app.schemas.evidence import Evidence
from app.schemas.user_query import TravelAgentState

_CHARGE_POLICY_TERMS = (
    "收费吗",
    "要收费",
    "需要收费",
    "需要门票",
    "要门票",
    "收门票",
    "免门票",
    "免费吗",
    "免费不",
)

_FREE_POLICY_RE = re.compile(
    r"(免费开放|免费进入|无需门票|不需要门票|不用门票|不收门票|免门票|免收门票|"
    r"(?:主街区|街区|开放区域|公共区域|外围|景区|景点)[^。；，、]{0,20}免费)"
)

_LIMITED_FREE_TERMS = (
    "儿童",
    "老人",
    "老年",
    "学生",
    "军人",
    "消防",
    "残疾",
    "身高",
    "周岁",
    "半价",
    "优惠",
    "活动",
    "预约数量",
    "名额",
)

_PAID_SUBITEM_TERMS = (
    "单独购票",
    "另行购票",
    "另收费",
    "单独收费",
    "部分景点收费",
    "内部景点",
    "体验项目",
    "演出",
    "游船",
    "夜游",
    "观光车",
    "联票",
    "套票",
)

_INTERNAL_ITEM_HINTS = (
    "大成殿",
    "科举",
    "博物馆",
    "陈列",
    "纪念馆",
    "故居",
    "瞻园",
    "中华门",
    "大报恩寺",
    "王谢",
    "李香君",
    "秦大士",
    "游船",
    "夜游",
    "观光车",
    "联票",
    "套票",
    "演出",
    "体验",
)


def is_ticket_charge_policy_query(state: TravelAgentState) -> bool:
    query = str(state.raw_user_query or "")
    return any(term in query for term in _CHARGE_POLICY_TERMS)


def build_ticket_area_policy(
    state: TravelAgentState,
    ticket_facts: list[dict[str, Any]],
    *,
    place_name: str,
) -> dict[str, Any] | None:
    if not is_ticket_charge_policy_query(state):
        return None
    free_lines = _free_policy_lines(list(state.evidence or []), place_name=place_name)
    if not free_lines:
        if _has_only_ambiguous_platform_ticket(ticket_facts):
            return {
                "mode": "ambiguous_platform_ticket",
                "free_policy_lines": [],
                "paid_scope_lines": [],
                "guidance": (
                    f"本轮只拿到平台票务商品价，尚不能确认它就是{place_name}整体入园票。"
                ),
            }
        return None
    paid_lines = [
        line
        for line in _paid_scope_lines(list(state.evidence or []), place_name=place_name)
        if _line_key(line) not in {_line_key(free) for free in free_lines}
    ]
    return {
        "mode": "open_area_with_paid_subitems",
        "free_policy_lines": free_lines[:3],
        "paid_scope_lines": paid_lines[:3],
        "guidance": (
            f"当前证据更支持：{place_name}的开放街区/公共游览区域不按「大门票」收费；"
            "平台票价应作为内部景点、体验项目或套餐候选核对。"
        ),
    }


def ticket_fact_scope_label(row: dict[str, Any], *, area_policy: dict[str, Any] | None = None) -> str:
    name = str(row.get("ticket_name") or row.get("summary_line") or row.get("raw_text") or "")
    if any(term in name for term in _INTERNAL_ITEM_HINTS):
        return "内部景点/项目票"
    if area_policy and str(row.get("source_class") or "").lower() in {"ticket_platform", "platform"}:
        return "平台票务商品候选"
    return "票价线索"


def _free_policy_lines(evidence: list[Evidence], *, place_name: str) -> list[str]:
    out: list[str] = []
    for ev in evidence:
        if not isinstance(ev, Evidence):
            continue
        text = _claim_text(ev)
        scope_text = f"{ev.place_name or ''} {text}"
        if not text or not _mentions_scope(scope_text, place_name):
            continue
        match = _FREE_POLICY_RE.search(text)
        if not match:
            continue
        window = text[max(0, match.start() - 24) : match.end() + 24]
        if any(term in window for term in _LIMITED_FREE_TERMS):
            continue
        out.append(_source_line(window, ev))
    return _dedupe(out)


def _paid_scope_lines(evidence: list[Evidence], *, place_name: str) -> list[str]:
    out: list[str] = []
    for ev in evidence:
        if not isinstance(ev, Evidence):
            continue
        text = _claim_text(ev)
        scope_text = f"{ev.place_name or ''} {text}"
        if not text or not _mentions_scope(scope_text, place_name):
            continue
        if not any(term in text for term in _PAID_SUBITEM_TERMS):
            continue
        idxs = [text.find(term) for term in _PAID_SUBITEM_TERMS if text.find(term) >= 0]
        idx = min(idxs) if idxs else 0
        snippet = text[max(0, idx - 28) : idx + 60]
        out.append(_source_line(snippet, ev))
    return _dedupe(out)


def _claim_text(ev: Evidence) -> str:
    parts: list[str] = []
    for claim in ev.claims or []:
        parts.extend([str(claim.value or ""), str(claim.raw_text or ""), str(claim.normalized_value or "")])
    return " ".join(p for p in parts if p).strip()


def _mentions_scope(text: str, place_name: str) -> bool:
    place = str(place_name or "").strip()
    return not place or place in text or "景区" in text or "街区" in text or "风光带" in text


def _source_line(snippet: str, ev: Evidence) -> str:
    source = ev.source_name or "证据"
    url = ev.source_url or ""
    line = f"{snippet.strip()}（来源：{source}"
    if url:
        line += f"，{url}"
    return line + "）"


def _dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = _line_key(line)
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def _line_key(line: str) -> str:
    return re.sub(r"\s+", "", str(line or ""))


def _has_only_ambiguous_platform_ticket(ticket_facts: list[dict[str, Any]]) -> bool:
    if not ticket_facts:
        return False
    for row in ticket_facts:
        source = str(row.get("source_class") or "").lower()
        if source not in {"ticket_platform", "platform"}:
            return False
        name = str(row.get("ticket_name") or "")
        if any(term in name for term in _INTERNAL_ITEM_HINTS):
            continue
        if name and name not in {"大门票", "大门票 成人票", "成人票", "门票"}:
            return False
    return True
