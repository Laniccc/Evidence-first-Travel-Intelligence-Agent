"""Control tools for Agent Core phase and job state transitions."""

from __future__ import annotations

from app.orchestrator.agent_core_store import ensure_agent_core_store, project_agent_core
from app.schemas.agent_core import ControlToolResult
from app.schemas.user_query import TravelAgentState


class AgentCoreControlTools:
    """Tool-like facade for state transitions.

    Phase tools produce outputs; these control tools are the only Agent Core
    surface that intentionally changes phase/job status.
    """

    def approve_phase(
        self,
        state: TravelAgentState,
        *,
        phase: str,
        output_id: str | None = None,
        approved_by: str = "root_agent",
    ) -> ControlToolResult:
        try:
            store = ensure_agent_core_store(state)
            record = store.approve_phase(phase, output_id=output_id, approved_by=approved_by)
            return ControlToolResult(
                tool_name="approve_phase",
                status="succeeded",
                message=f"approved {phase}",
                phase=record.phase,
                projection=project_agent_core(state),
            )
        except Exception as exc:
            return ControlToolResult(
                tool_name="approve_phase",
                status="failed",
                message=str(exc),
                phase=phase,
                projection=project_agent_core(state),
            )

    def rollback_to_phase(
        self,
        state: TravelAgentState,
        *,
        phase: str,
        reason: str,
    ) -> ControlToolResult:
        try:
            store = ensure_agent_core_store(state)
            record = store.rollback_to_phase(phase, reason=reason)
            return ControlToolResult(
                tool_name="rollback_to_phase",
                status="succeeded",
                message=f"rolled back to {phase}: {reason}",
                phase=record.phase,
                projection=project_agent_core(state),
            )
        except Exception as exc:
            return ControlToolResult(
                tool_name="rollback_to_phase",
                status="failed",
                message=str(exc),
                phase=phase,
                projection=project_agent_core(state),
            )

    def reconcile_job(
        self,
        state: TravelAgentState,
        *,
        job_id: str,
        status: str | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> ControlToolResult:
        try:
            store = ensure_agent_core_store(state)
            record = store.update_job(
                job_id,
                status=status,
                output_ref=output_ref,
                error=error,
            )
            return ControlToolResult(
                tool_name="reconcile_job",
                status="succeeded",
                message=f"job {record.id} is {record.status}",
                job_id=record.id,
                projection=project_agent_core(state),
            )
        except Exception as exc:
            return ControlToolResult(
                tool_name="reconcile_job",
                status="failed",
                message=str(exc),
                job_id=job_id,
                projection=project_agent_core(state),
            )
