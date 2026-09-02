"""Public contracts for the single auditable Agent state runtime."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.governance.failure_reason import FailureClass
from app.governance.tool_budget import RunBudget


class AgentState(StrEnum):
    INGRESS = "ingress"
    CONTEXT = "context"
    UNDERSTAND = "understand"
    ROUTE = "route"
    CLARIFICATION = "clarification"
    FACT_QUERY = "fact_query"
    SUITABILITY = "suitability"
    COMPARISON = "comparison"
    RAG_RETRIEVE = "rag_retrieve"
    LIVE_GAP_FILL = "live_gap_fill"
    EVIDENCE_EVALUATE = "evidence_evaluate"
    COMPOSE = "compose"
    CITATION_GUARD = "citation_guard"
    LIMITED_ANSWER = "limited_answer"
    SAFE_FAILURE = "safe_failure"
    DELIVER = "deliver"
    FAILED = "failed"


TERMINAL_STATES = frozenset(
    {
        AgentState.CLARIFICATION,
        AgentState.LIMITED_ANSWER,
        AgentState.SAFE_FAILURE,
        AgentState.DELIVER,
        AgentState.FAILED,
    }
)


class StateFailure(BaseModel):
    category: FailureClass
    code: str
    message: str
    recoverable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class RecoveryRecord(BaseModel):
    strategy: str
    recovered_from: FailureClass
    attempt: int = Field(ge=1)


class StatePolicy(BaseModel):
    timeout_seconds: float = Field(default=10.0, gt=0)
    max_attempts: int = Field(default=1, ge=1, le=3)


class StateContext(BaseModel):
    run_id: str
    session_id: str
    query_id: str
    raw_query: str = Field(exclude=True)
    trace_id: str | None = None
    current_state: AgentState = AgentState.INGRESS
    artifacts: dict[str, Any] = Field(default_factory=dict)
    versions: dict[str, str] = Field(default_factory=dict)
    config_hashes: dict[str, str] = Field(default_factory=dict)
    budget: RunBudget = Field(default_factory=RunBudget)


class StateResult(BaseModel):
    status: Literal["succeeded", "failed", "recovered"]
    next_state: AgentState
    output: dict[str, Any] = Field(default_factory=dict)
    failure: StateFailure | None = None
    recovery: RecoveryRecord | None = None

    @classmethod
    def succeeded(
        cls,
        *,
        next_state: AgentState,
        output: dict[str, Any] | None = None,
    ) -> "StateResult":
        return cls(status="succeeded", next_state=next_state, output=output or {})

    @classmethod
    def failed(
        cls,
        *,
        failure: StateFailure,
        next_state: AgentState = AgentState.FAILED,
        output: dict[str, Any] | None = None,
    ) -> "StateResult":
        return cls(
            status="failed",
            next_state=next_state,
            output=output or {},
            failure=failure,
        )


class StateRunResult(BaseModel):
    terminal_state: AgentState
    context: StateContext
    failure: StateFailure | None = None
    steps: int = Field(default=0, ge=0)


class StateHandler(Protocol):
    async def run(self, context: StateContext) -> StateResult:
        ...


__all__ = [
    "AgentState",
    "FailureClass",
    "RecoveryRecord",
    "StateContext",
    "StateFailure",
    "StateHandler",
    "StatePolicy",
    "StateResult",
    "StateRunResult",
    "TERMINAL_STATES",
]
