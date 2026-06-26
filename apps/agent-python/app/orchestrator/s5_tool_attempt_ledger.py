"""Track S5 MCP tool attempts across main loop, sub-agents, gap-fill, and supplement."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name

Phase = Literal["main", "gap_fill", "supplement", "subagent"]
AttemptStatus = Literal["ok", "error", "zero_evidence", "skipped_invalid_args"]


class ToolAttemptRecord(BaseModel):
    tool_name: str
    claim_type: str | None = None
    subagent: str | None = None
    phase: Phase = "main"
    status: AttemptStatus = "ok"
    evidence_count: int = 0
    error: str | None = None


class S5ToolAttemptLedger(BaseModel):
    records: list[ToolAttemptRecord] = Field(default_factory=list)

    def attempted_tools(
        self,
        *,
        claim_type: str | None = None,
        subagent: str | None = None,
        phase: Phase | None = None,
    ) -> set[str]:
        out: set[str] = set()
        for rec in self.records:
            if claim_type and rec.claim_type and rec.claim_type != claim_type:
                continue
            if subagent and rec.subagent and rec.subagent != subagent:
                continue
            if phase and rec.phase != phase:
                continue
            if rec.status != "skipped_invalid_args":
                out.add(resolve_tool_name(rec.tool_name))
        return out

    def attempt_count(self, tool_name: str, *, claim_type: str | None = None) -> int:
        resolved = resolve_tool_name(tool_name)
        count = 0
        for rec in self.records:
            if resolve_tool_name(rec.tool_name) != resolved:
                continue
            if claim_type and rec.claim_type and rec.claim_type != claim_type:
                continue
            if rec.status == "skipped_invalid_args":
                continue
            count += 1
        return count

    def record(self, entry: ToolAttemptRecord) -> None:
        entry.tool_name = resolve_tool_name(entry.tool_name)
        self.records.append(entry)

    def sync_from_tool_traces(self, state: TravelAgentState) -> None:
        """Backfill ledger from existing traces (idempotent per trace index)."""
        structured = dict(state.structured_result or {})
        synced = int(structured.get("_ledger_synced_trace_count") or 0)
        traces = state.tool_traces or []
        if synced >= len(traces):
            return
        phase: Phase = "gap_fill" if state.current_evidence_gap_request else "main"
        for trace in traces[synced:]:
            resolved = resolve_tool_name(trace.tool_name)
            if not resolved:
                continue
            if any(
                resolve_tool_name(r.tool_name) == resolved
                and r.phase == phase
                for r in self.records[-20:]
            ):
                continue
            status: AttemptStatus = "error" if trace.status == "error" else "ok"
            ev_count = len(trace.evidence_ids or [])
            if status == "ok" and ev_count == 0:
                status = "zero_evidence"
            claim = trace.gap_claim_type
            if not claim and isinstance(trace.input, dict):
                claim = trace.input.get("claim_target") or trace.input.get("information_need")
            self.record(
                ToolAttemptRecord(
                    tool_name=resolved,
                    claim_type=str(claim) if claim else None,
                    phase="gap_fill" if trace.gap_filling else phase,
                    status=status,
                    evidence_count=ev_count,
                    error=trace.error,
                )
            )
        structured["_ledger_synced_trace_count"] = len(traces)
        state.structured_result = structured


def get_ledger(state: TravelAgentState) -> S5ToolAttemptLedger:
    structured = state.structured_result or {}
    raw = structured.get("s5_tool_attempt_ledger")
    if isinstance(raw, dict):
        ledger = S5ToolAttemptLedger.model_validate(raw)
    elif isinstance(raw, S5ToolAttemptLedger):
        ledger = raw
    else:
        ledger = S5ToolAttemptLedger()
    ledger.sync_from_tool_traces(state)
    return ledger


def save_ledger(state: TravelAgentState, ledger: S5ToolAttemptLedger) -> None:
    structured = dict(state.structured_result or {})
    structured["s5_tool_attempt_ledger"] = ledger.model_dump()
    state.structured_result = structured


def record_tool_attempt(
    state: TravelAgentState,
    *,
    tool_name: str,
    claim_type: str | None = None,
    subagent: str | None = None,
    phase: Phase = "main",
    status: AttemptStatus = "ok",
    evidence_count: int = 0,
    error: str | None = None,
) -> None:
    ledger = get_ledger(state)
    ledger.record(
        ToolAttemptRecord(
            tool_name=resolve_tool_name(tool_name),
            claim_type=claim_type,
            subagent=subagent,
            phase=phase,
            status=status,
            evidence_count=evidence_count,
            error=error,
        )
    )
    save_ledger(state, ledger)
