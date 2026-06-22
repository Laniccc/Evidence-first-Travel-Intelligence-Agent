"""Write the latest query answer and thinking trace to a debug markdown file (overwrite each turn)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.response import TravelQueryResponse

_DEBUG_MD = Path(__file__).resolve().parent.parent / "debug_last_session.md"


def debug_session_path() -> Path:
    return _DEBUG_MD


def write_debug_session_md(query: str, result: TravelQueryResponse) -> Path:
    """Overwrite debug markdown with the latest conversation output and trace."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# Travel Agent - Last Session Debug",
        "",
        f"- **Time**: {now}",
        f"- **Query ID**: {result.query_id or '-'}",
        f"- **Session ID**: {result.session_id or '-'}",
        f"- **Confidence**: {result.confidence:.2f}",
        f"- **Answer mode**: {result.answer_mode or '-'}",
        "",
        "## User Query",
        "",
        query.strip() or "(empty)",
        "",
        "## Final Answer",
        "",
        (result.answer or "").strip() or "_(no answer text)_",
        "",
        "## Thinking / Trace",
        "",
    ]

    if result.visible_trace:
        for i, step in enumerate(result.visible_trace, 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("_(no trace steps)_")

    if result.limitations:
        lines.extend(["", "## Limitations", ""])
        for item in result.limitations:
            lines.append(f"- {item}")

    if result.evidence_summary:
        lines.extend(["", "## Evidence Summary", "", "```json"])
        lines.append(json.dumps(result.evidence_summary, ensure_ascii=False, indent=2))
        lines.append("```")

    if result.tool_traces:
        lines.extend(["", "## Tool Traces", "", "```json"])
        lines.append(json.dumps(result.tool_traces, ensure_ascii=False, indent=2))
        lines.append("```")

    if result.semantic_frame_summary:
        lines.extend(["", "## Semantic Frame", "", "```json"])
        lines.append(json.dumps(result.semantic_frame_summary, ensure_ascii=False, indent=2))
        lines.append("```")

    lines.append("")
    path = debug_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path