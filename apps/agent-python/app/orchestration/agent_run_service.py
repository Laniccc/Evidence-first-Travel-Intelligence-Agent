"""Thin facade over the current Agent state machine."""

from typing import Any, Callable, Protocol
from uuid import uuid4

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
        debug_enabled: bool = True,
    ):
        self._state_machine = state_machine
        self._debug_writer = debug_writer
        self._logger = logger
        self._debug_enabled = debug_enabled

    async def query(
        self, payload: AgentQueryRequest, *, trace_id: str | None = None
    ) -> AgentQueryResponse:
        trace_id = trace_id or str(uuid4())
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
            trace_id=trace_id,
        )
        response = (
            result
            if isinstance(result, AgentQueryResponse)
            else AgentQueryResponse.from_legacy(result, session_id=session_context.session_id)
        )
        if payload.debug and self._debug_enabled:
            try:
                self._debug_writer(session_context.query, response)
            except Exception as exc:
                self._logger.warning("debug_session_log_failed", error=str(exc))
        summary = response.orchestration_summary or {}
        info = getattr(self._logger, "info", None)
        if info is not None:
            info(
                "agent_run_completed",
                query_id=response.query_id,
                session_id=response.session_id,
                trace_id=trace_id,
                terminal_state=summary.get("terminal_state"),
                run_id=summary.get("run_id"),
            )
        return response


def create_agent_run_service(
    debug_writer: Callable[[str, Any], None],
    logger,
    *,
    state_machine: AgentStateMachine | None = None,
    debug_enabled: bool = True,
) -> AgentRunService:
    return AgentRunService(
        state_machine=state_machine or TravelAgentStateMachine(),
        debug_writer=debug_writer,
        logger=logger,
        debug_enabled=debug_enabled,
    )
