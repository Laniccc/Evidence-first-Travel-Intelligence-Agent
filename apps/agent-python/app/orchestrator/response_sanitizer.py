"""User-facing response cleanup.

The planner and tool layers keep detailed diagnostics in traces.  This module
keeps those diagnostics available for debug files while preventing them from
leaking into the final answer/limitations shown to users.
"""

from __future__ import annotations

import re

_INTERNAL_LIMITATION_RE = re.compile(
    r"S5 gap-fill|gap-fill completed|Missing source URL|requires urls or search_results|"
    r"requires a readable url|No claims in evidence|Low confidence evidence from|"
    r"coverage=|adoption=|claim_type|evidence_id|mock 数据|结构化 mock|"
    r"暂无结构化|Answer composition FINISH|LLM review produced|"
    r"official_source_discovery_mcp|open-webSearch|fetch-web|"
    r"mcp_server=|mcp_tool=|fallback_used=true|"
    r"WinError|系统找不到指定的文件|"
    r"Java Tool Gateway|policy 拒绝|not allowed in current lookup phase",
    re.I,
)

_INTERNAL_ANSWER_LINE_RE = re.compile(
    r"overall_confidence|coverage=|adoption=|claim_type|evidence_id|证据ID|"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"
    r"Mock|模拟数据|Transit API Mock|尝试工具|coverage_report|"
    r"Forbidden City|fact_sheet|curated_claims",
    re.I,
)

_NOISY_CONTEXT_RE = re.compile(
    r"未提供出行日期|未提供同行人画像|按一般游客评估|默认近日假设|"
    r"体验判断缺少 fact_sheet|答案中某些具体表述未能与证据值完全匹配",
    re.I,
)

_DUPLICATE_WHITESPACE_RE = re.compile(r"\n{3,}")


def is_user_visible_limitation(text: str) -> bool:
    """Return False for internal diagnostics or low-value generic assumptions."""
    value = str(text or "").strip()
    if not value:
        return False
    if _INTERNAL_LIMITATION_RE.search(value):
        return False
    if _NOISY_CONTEXT_RE.search(value):
        return False
    return True


def sanitize_limitations(limitations: list[str] | None, *, max_items: int = 5) -> list[str]:
    """Dedupe and filter limitations for final user-visible responses."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in limitations or []:
        text = str(raw or "").strip()
        if not is_user_visible_limitation(text):
            continue
        normalized = re.sub(r"\s+", " ", text)
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def sanitize_answer_text(answer: str | None) -> str:
    """Drop lines that expose internal S5/tool diagnostics."""
    if not answer:
        return ""
    kept: list[str] = []
    for line in str(answer).splitlines():
        stripped = line.strip()
        bullet_text = stripped.lstrip("-*0123456789.、) ").strip()
        if stripped and _INTERNAL_ANSWER_LINE_RE.search(stripped):
            continue
        if stripped and not is_user_visible_limitation(bullet_text):
            continue
        kept.append(line.rstrip())
    text = "\n".join(kept).strip()
    return _DUPLICATE_WHITESPACE_RE.sub("\n\n", text)
