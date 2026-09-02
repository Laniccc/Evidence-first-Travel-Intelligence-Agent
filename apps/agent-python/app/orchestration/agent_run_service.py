"""Thin facade over the current Agent state machine."""

from typing import Any, Callable, Protocol

from app.context.session_context import SessionContext
from app.contracts.request import AgentQueryRequest
from app.contracts.response import AgentQueryResponse
from app.orchestration.state_machine import TravelAgentStateMachine


class AgentStateMachine(Protocol):
    async def run(
        self,
        query: str,
        user_context: dict,
        session_id: str | None = None,
        *,
        debug: bool = False,
        trace_id: str | None = None,
    ) -> Any:
        ...


class AgentRunService:
    def __init__(
        self,
        state_machine: AgentStateMachine,
        debug_writer: Callable[[str, Any], None],
        logger,
    ):
        self._state_machine = state_machine
        self._debug_writer = debug_writer
        self._logger = logger

    async def query(self, payload: AgentQueryRequest) -> AgentQueryResponse:
        session_context = SessionContext.from_java_payload(
            query=payload.query,
            session_id=payload.session_id,
            user_context=payload.user_context,
        )

        result = await self._state_machine.run(
            session_context.query,
            session_context.to_agent_user_context(),
            session_context.session_id,
            debug=payload.debug,
            trace_id=None,
        )
        if payload.debug:
            try:
                self._debug_writer(session_context.query, result)
            except Exception as exc:
                self._logger.warning("debug_session_log_failed", error=str(exc))
        return AgentQueryResponse.from_legacy(result, session_id=session_context.session_id)


def create_agent_run_service(debug_writer: Callable[[str, Any], None], logger) -> AgentRunService:
    return AgentRunService(
        state_machine=TravelAgentStateMachine(),
        debug_writer=debug_writer,
        logger=logger,
    )
