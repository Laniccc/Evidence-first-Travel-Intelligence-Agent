"""Audit event models that deliberately exclude raw prompts and chain-of-thought."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.orchestration.state_contracts import (
    AgentState,
    RecoveryRecord,
    StateContext,
    StateFailure,
)


AuditEventType = Literal[
    "phase_started",
    "phase_succeeded",
    "phase_failed",
    "phase_recovered",
    "transition_committed",
]


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class StateAuditEvent(BaseModel):
    event_type: AuditEventType
    run_id: str
    session_id: str
    query_id: str
    trace_id: str | None = None
    state: AgentState
    attempt: int = Field(ge=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float | None = Field(default=None, ge=0)
    status: str
    input_ref: str | None = None
    output_ref: str | None = None
    input_digest: str | None = None
    output_digest: str | None = None
    failure: StateFailure | None = None
    recovery: RecoveryRecord | None = None
    from_state: AgentState | None = None
    to_state: AgentState | None = None
    versions: dict[str, str] = Field(default_factory=dict)
    config_hashes: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def started(
        cls,
        context: StateContext,
        state: AgentState,
        *,
        attempt: int,
    ) -> "StateAuditEvent":
        return cls(
            event_type="phase_started",
            run_id=context.run_id,
            session_id=context.session_id,
            query_id=context.query_id,
            trace_id=context.trace_id,
            state=state,
            attempt=attempt,
            status="running",
            input_ref=f"{context.run_id}:{state.value}:attempt:{attempt}:input",
            input_digest=_digest(
                {
                    "artifact_keys": sorted(context.artifacts),
                    "state": state.value,
                    "budget": context.budget.model_dump(mode="json"),
                }
            ),
            versions=context.versions,
            config_hashes=context.config_hashes,
        )

    @classmethod
    def completed(
        cls,
        context: StateContext,
        state: AgentState,
        *,
        attempt: int,
        output: dict[str, Any],
        duration_ms: float,
        recovered: RecoveryRecord | None = None,
    ) -> "StateAuditEvent":
        return cls(
            event_type="phase_recovered" if recovered else "phase_succeeded",
            run_id=context.run_id,
            session_id=context.session_id,
            query_id=context.query_id,
            trace_id=context.trace_id,
            state=state,
            attempt=attempt,
            duration_ms=duration_ms,
            status="recovered" if recovered else "succeeded",
            output_ref=f"{context.run_id}:{state.value}:attempt:{attempt}:output",
            output_digest=_digest(output),
            recovery=recovered,
            versions=context.versions,
            config_hashes=context.config_hashes,
        )

    @classmethod
    def failed(
        cls,
        context: StateContext,
        state: AgentState,
        *,
        attempt: int,
        failure: StateFailure,
        duration_ms: float | None = None,
    ) -> "StateAuditEvent":
        return cls(
            event_type="phase_failed",
            run_id=context.run_id,
            session_id=context.session_id,
            query_id=context.query_id,
            trace_id=context.trace_id,
            state=state,
            attempt=attempt,
            duration_ms=duration_ms,
            status="failed",
            failure=failure,
            versions=context.versions,
            config_hashes=context.config_hashes,
        )

    @classmethod
    def transition(
        cls,
        context: StateContext,
        *,
        from_state: AgentState,
        to_state: AgentState,
        attempt: int,
    ) -> "StateAuditEvent":
        return cls(
            event_type="transition_committed",
            run_id=context.run_id,
            session_id=context.session_id,
            query_id=context.query_id,
            trace_id=context.trace_id,
            state=from_state,
            attempt=attempt,
            status="committed",
            from_state=from_state,
            to_state=to_state,
            versions=context.versions,
            config_hashes=context.config_hashes,
        )


class StateAuditStore(Protocol):
    def append(self, event: StateAuditEvent) -> None:
        ...

    def for_run(self, run_id: str) -> list[StateAuditEvent]:
        ...


class InMemoryStateAuditStore:
    def __init__(self) -> None:
        self.events: list[StateAuditEvent] = []

    def append(self, event: StateAuditEvent) -> None:
        self.events.append(event)

    def for_run(self, run_id: str) -> list[StateAuditEvent]:
        return [event for event in self.events if event.run_id == run_id]
