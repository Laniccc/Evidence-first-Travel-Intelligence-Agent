"""Write the latest research query result to a debug markdown file (overwrite each turn)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEBUG_MD = Path(__file__).resolve().parent.parent / "debug_last_session.md"

DIAG_PHASES = [
    "planning",
    "knowledge_retrieval",
    "evidence_acquisition",
    "evidence_extraction",
    "synthesis",
    "knowledge_upsert",
]


def debug_session_path() -> Path:
    return _DEBUG_MD


def write_debug_session(*, query: str, result: dict[str, Any]) -> Path:
    """Overwrite debug markdown with the latest research pipeline result."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    run_id = result.get("run_id") or "-"
    status = result.get("status") or "unknown"
    phases = result.get("phases_completed") or []
    evidence_count = result.get("evidence_count") or 0
    report = result.get("report") or {}

    lines: list[str] = [
        "# Deep Research Agent — Last Session Debug",
        "",
        f"- **Time**: {now}",
        f"- **Run ID**: `{run_id}`",
        f"- **Status**: {status}",
        f"- **Phases completed**: {len(phases)}/6",
        f"- **Evidence records**: {evidence_count}",
    ]

    # ── Phase trace ──
    lines.extend(["", "## Phase Trace", ""])
    lines.append("| # | Phase | Result |")
    lines.append("|---|---|")
    for i, p in enumerate(DIAG_PHASES, 1):
        done = p in phases
        icon = "OK" if done else "--"
        lines.append(f"| {i} | `{p}` | {icon} |")

    # ── Errors ──
    errors = result.get("errors") or []
    if errors:
        lines.extend(["", "## Errors", ""])
        for e in errors:
            lines.append(f"- {e}")

    # ── Report ──
    if report:
        lines.extend(["", "## Report", ""])
        title = report.get("title") or "(untitled)"
        lines.append(f"### {title}")
        lines.append("")

        summary = report.get("summary") or ""
        if summary:
            lines.append(f"> {summary}")
            lines.append("")

        sections = report.get("sections") or []
        for s in sections:
            heading = s.get("heading") or ""
            content = s.get("content") or ""
            lines.append(f"#### {heading}")
            lines.append("")
            lines.append(content)
            lines.append("")

        citations = report.get("citations") or []
        if citations:
            lines.extend(["### Citations", ""])
            for c in citations:
                tid = c.get("id") or c.get("index") or "-"
                ttl = c.get("title") or c.get("url") or "-"
                url = c.get("url") or ""
                tier = c.get("tier") or "?"
                lines.append(f"- [{tid}] [{ttl}]({url}) — T{tier}")

        limitations = report.get("limitations") or []
        if limitations:
            lines.extend(["", "### Limitations", ""])
            for li in limitations:
                lines.append(f"- {li}")

        delivery_note = report.get("delivery_note") or ""
        if delivery_note:
            lines.extend(["", "### Delivery Note", "", delivery_note])

    # ── Evidence detail ──
    evidence_list = result.get("_evidence_detail") or []
    if evidence_list:
        lines.extend(["", "## Evidence Detail", ""])
        lines.append(f"Total: {len(evidence_list)} records")
        lines.append("")
        lines.append("| # | Source | URL | Tier |")
        lines.append("|---|---|---|---|")
        for i, ev in enumerate(evidence_list, 1):
            src = ev.get("source_name") or ev.get("source_type") or "?"
            url = ev.get("source_url") or ev.get("url") or "-"
            tier = ev.get("source_tier") or ev.get("tier") or "?"
            lines.append(f"| {i} | {src} | {url} | T{tier} |")

    # ── Raw result JSON ──
    # Dump everything except bulky evidence detail for full traceability
    slim = {k: v for k, v in result.items() if k != "_evidence_detail"}
    lines.extend(["", "## Raw Result", "", "```json"])
    lines.append(json.dumps(slim, ensure_ascii=False, indent=2, default=str))
    lines.append("```")
    lines.append("")

    path = debug_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
