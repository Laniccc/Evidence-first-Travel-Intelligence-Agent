"""Typed records for the compact runtime audit ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRecord(BaseModel):
    run_id: str
    query_id: str
    session_id: str
    query_digest: str
    status: str
    current_state: str
    replay_of_run_id: str | None = None
    created_at: str
    completed_at: str | None = None


class PhaseEventRecord(BaseModel):
    event_id: int
    run_id: str
    state: str
    status: str
    attempt: int
    output: dict[str, Any] = Field(default_factory=dict)
    failure_code: str | None = None
    recovery_strategy: str | None = None
    created_at: str


class RunInspection(BaseModel):
    run: RunRecord
    timeline: list[PhaseEventRecord] = Field(default_factory=list)
    execution_attempts: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    answer_claims: list[dict[str, Any]] = Field(default_factory=list)
    citation_decisions: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


__all__ = ["PhaseEventRecord", "RunInspection", "RunRecord", "utc_now_iso"]
