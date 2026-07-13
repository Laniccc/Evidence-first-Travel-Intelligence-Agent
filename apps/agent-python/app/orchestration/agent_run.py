"""One-run orchestration boundary owned by the Python Agent."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

TravelAgentState = Any


class AgentRun(BaseModel):
    session_id: str
    query: str
    query_id: str | None = None
    user_context: dict[str, Any] = Field(default_factory=dict)
    state: TravelAgentState | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_state(
        cls,
        state: TravelAgentState,
        *,
        user_context: dict[str, Any] | None = None,
    ) -> "AgentRun":
        return cls(
            session_id=state.session_id,
            query_id=state.query_id,
            query=state.raw_user_query,
            user_context=dict(user_context or {}),
            state=state,
        )

    def attach_state(self, state: TravelAgentState) -> "AgentRun":
        return self.model_copy(
            update={
                "session_id": state.session_id,
                "query_id": state.query_id,
                "query": state.raw_user_query,
                "state": state,
            }
        )
