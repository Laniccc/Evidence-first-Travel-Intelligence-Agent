"""Write the latest query answer and thinking trace to a debug markdown file (overwrite each turn)."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.response import TravelQueryResponse

_DEBUG_MD = Path(__file__).resolve().parent.parent / "debug_last_session.md"

_SUBAGENT_CALL_RE = re.compile(r"call_subagent\s*→\s*(\w+)", re.IGNORECASE)
_A2A_SUBAGENT_RE = re.compile(r"\[A2A\]\s+(\w+)", re.IGNORECASE)
_UNKNOWN_SUBAGENT_RE = re.compile(r"Unknown subagent:\s*(\w+)", re.IGNORECASE)


def debug_session_path() -> Path:
    return _DEBUG_MD


def _trace_subagent_diagnostics(visible_trace: list[str]) -> dict:
    calls: Counter[str] = Counter()
    a2a: Counter[str] = Counter()
    for step in visible_trace:
        for match in _SUBAGENT_CALL_RE.finditer(step):
            calls[match.group(1)] += 1
        for match in _A2A_SUBAGENT_RE.finditer(step):
            a2a[match.group(1)] += 1
    warnings: list[str] = []
    for name, count in sorted(calls.items()):
        if count > 1 and a2a.get(name, 0) == 0:
            warnings.append(
                f"`{name}` delegated {count}× but no `✓ [A2A] {name}` — "
                "check action_executor registration and state_reducer merge"
            )
        elif count > 5 and a2a.get(name, 0) < count // 2:
            warnings.append(f"`{name}` delegated {count}× — possible S5 loop")
    return {"delegations": dict(calls), "a2a_merges": dict(a2a), "warnings": warnings}


def _limitations_diagnostics(limitations: list[str]) -> dict:
    unknown: Counter[str] = Counter()
    other: list[str] = []
    for item in limitations or []:
        match = _UNKNOWN_SUBAGENT_RE.search(item)
        if match:
            unknown[match.group(1)] += 1
        else:
            other.append(item)
    return {"unknown_subagents": dict(unknown), "other": other}


def _tool_trace_rollup(tool_traces: list[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in tool_traces:
        name = row.get("tool_name") or row.get("tool") or "unknown"
        counts[str(name)] += 1
    return dict(counts.most_common())


def _format_lookup_orchestration(summary: dict) -> list[str]:
    lines: list[str] = []
    task_class = summary.get("s5_task_class")
    if task_class:
        lines.append(f"- **S5 task class**: `{task_class}`")
    anchor = summary.get("fact_anchor")
    if anchor:
        lines.append(
            f"- **Fact anchor**: {anchor.get('resolved_name') or anchor.get('raw_place')} "
            f"({anchor.get('city') or '-'}, {anchor.get('province') or '-'})"
        )
    sub_results = summary.get("subagent_results") or []
    fact_rows = [r for r in sub_results if r.get("subagent") == "fact_lookup_agent"]
    if fact_rows:
        last = fact_rows[-1]
        lines.append(
            f"- **fact_lookup_agent**: evidence_count={last.get('evidence_count', '?')}, "
            f"task_id={last.get('task_id', '-')}"
        )
    pipeline_runs = summary.get("fact_lookup_pipeline_runs") or []
    chain = summary.get("lookup_research_chain") or {}
    if chain:
        lines.append(
            f"- **LookupResearchChain**: phase={chain.get('current_phase')}, "
            f"completed={chain.get('completed_phases') or []}"
        )
        audit = chain.get("audit") or {}
        if audit:
            lines.append(
                f"- **Retrieval audit**: recommended_next={audit.get('recommended_next')}, "
                f"official_fact_found={audit.get('official_fact_found')}"
            )
        objectives = chain.get("query_objectives") or []
        if objectives:
            lines.append(
                f"- **Query objectives**: {len(objectives)} active "
                f"({objectives[0].get('source_family', '?') if objectives else '-'})"
            )
    if fact_rows:
        phases = [r.get("lookup_phase") for r in fact_rows if r.get("lookup_phase")]
        families = [r.get("source_family") for r in fact_rows if r.get("source_family")]
        if phases or families:
            lines.append(
                f"- **fact_lookup runs**: phases={phases[-3:]}, families={families[-3:]}"
            )
    if pipeline_runs:
        last_run = pipeline_runs[-1]
        queries = last_run.get("search_queries") or []
        lines.append(
            f"- **Pipeline**: tools={last_run.get('tool_call_count', '?')}, "
            f"claims={last_run.get('actionable_claims', '?')}, "
            f"official={last_run.get('has_official')}, geo={last_run.get('has_authoritative_geo')}"
        )
        if queries:
            lines.append(f"- **Search queries**: {', '.join(queries[:3])}")
    return lines


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
    ]

    lim_diag = _limitations_diagnostics(result.limitations or [])
    if lim_diag["unknown_subagents"]:
        lines.extend(["", "## Execution Issues", ""])
        for name, count in sorted(lim_diag["unknown_subagents"].items()):
            lines.append(
                f"- **CRITICAL**: `Unknown subagent: {name}` ×{count} — "
                f"register `{name}` in `action_executor._call_subagent`"
            )

    if result.orchestration_summary:
        lookup_lines = _format_lookup_orchestration(result.orchestration_summary)
        lines.extend(["", "## Orchestration Summary", ""])
        if lookup_lines:
            lines.extend(lookup_lines)
        lines.extend(["", "```json"])
        lines.append(
            json.dumps(result.orchestration_summary, ensure_ascii=False, indent=2, default=str)
        )
        lines.append("```")

    diag = _trace_subagent_diagnostics(result.visible_trace or [])
    if diag["delegations"] or diag["warnings"]:
        lines.extend(["", "## S5 Subagent Diagnostics", ""])
        if diag["delegations"]:
            lines.append(
                "Delegations: " + ", ".join(f"{k}×{v}" for k, v in sorted(diag["delegations"].items()))
            )
        if diag["a2a_merges"]:
            lines.append("A2A merges: " + ", ".join(f"{k}×{v}" for k, v in sorted(diag["a2a_merges"].items())))
        for warning in diag["warnings"]:
            lines.append(f"- ⚠ {warning}")

    if result.tool_traces:
        rollup = _tool_trace_rollup(result.tool_traces)
        if rollup:
            lines.extend(["", "## Tool Call Rollup", ""])
            for name, count in rollup.items():
                lines.append(f"- {name}: {count}")

    lines.extend(["", "## Thinking / Trace", ""])

    if result.visible_trace:
        for i, step in enumerate(result.visible_trace, 1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("_(no trace steps)_")

    if lim_diag["other"] or lim_diag["unknown_subagents"]:
        lines.extend(["", "## Limitations", ""])
        for name, count in sorted(lim_diag["unknown_subagents"].items()):
            if count > 1:
                lines.append(f"- Unknown subagent: {name} (×{count}, see Execution Issues)")
            else:
                lines.append(f"- Unknown subagent: {name}")
        for item in lim_diag["other"]:
            lines.append(f"- {item}")

    if result.evidence_summary:
        lines.extend(["", "## Evidence Summary", "", "```json"])
        lines.append(json.dumps(result.evidence_summary, ensure_ascii=False, indent=2, default=str))
        lines.append("```")

    if result.tool_traces:
        lines.extend(["", "## Tool Traces", "", "```json"])
        lines.append(json.dumps(result.tool_traces, ensure_ascii=False, indent=2, default=str))
        lines.append("```")

    if result.semantic_frame_summary:
        lines.extend(["", "## Semantic Frame", "", "```json"])
        lines.append(json.dumps(result.semantic_frame_summary, ensure_ascii=False, indent=2, default=str))
        lines.append("```")

    lines.append("")
    path = debug_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
