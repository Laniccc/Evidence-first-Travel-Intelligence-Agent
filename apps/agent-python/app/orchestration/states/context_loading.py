"""Session context loading with an explicit degraded-history path."""

from __future__ import annotations

from typing import Any, Protocol

from app.context.session_context import ContextSnapshot, SessionContext
from app.governance.failure_reason import FailureClass
from app.orchestration.state_contracts import (
    AgentState,
    RecoveryRecord,
    StateContext,
    StateResult,
)


class HistoryLoader(Protocol):
    def load(self, session_id: str) -> dict[str, Any] | None: ...


class ContextLoadingHandler:
    def __init__(self, *, history_loader: HistoryLoader | None = None) -> None:
        self._history_loader = history_loader

    async def run(self, context: StateContext) -> StateResult:
        user_context = dict(context.user_context)
        recovery = None
        history_status = "not_configured"
        if self._history_loader:
            try:
                history = self._history_loader.load(context.session_id) or {}
                user_context = {**history, **user_context}
                history_status = "loaded"
            except Exception:
                history_status = "unavailable"
                recovery = RecoveryRecord(
                    strategy="history_unavailable",
                    recovered_from=FailureClass.DEPENDENCY_UNAVAILABLE,
                    attempt=1,
                )

        session = SessionContext.from_java_payload(
            query=context.raw_query,
            session_id=context.session_id,
            user_context=user_context,
        )
        snapshot = ContextSnapshot.from_session(session)
        output = {
            "snapshot": snapshot.model_dump(mode="json"),
            "history_status": history_status,
        }
        if recovery:
            return StateResult(
                status="recovered",
                next_state=AgentState.UNDERSTAND,
                output=output,
                recovery=recovery,
            )
        return StateResult.succeeded(next_state=AgentState.UNDERSTAND, output=output)


__all__ = ["ContextLoadingHandler", "HistoryLoader"]
