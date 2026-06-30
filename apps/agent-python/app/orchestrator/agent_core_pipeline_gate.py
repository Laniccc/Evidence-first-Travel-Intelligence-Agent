"""Experimental Pipeline Gate for Agent Core tool visibility."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.orchestrator.agent_core_data_tool_policy import (
    DATA_TOOL_PHASES,
    DataToolVisibilityPolicy,
)
from app.orchestrator.agent_core_store import project_agent_core
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.capability_registry import CapabilityRegistry


class ToolVisibility(BaseModel):
    phase: str
    allowed_tools: list[str] = Field(default_factory=list)
    control_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[dict[str, str]] = Field(default_factory=list)
    required_next_actions: list[str] = Field(default_factory=list)
    stop_reasons: list[str] = Field(default_factory=list)
    decision_sources: list[str] = Field(default_factory=list)
    projection: dict[str, Any] | None = None
    tool_whitelist: ToolWhitelist | None = Field(default=None, exclude=True)


class PipelineGate:
    """Single entry point for Root Agent tool visibility.

    For now this wraps the existing ToolWhitelistBuilder. The important
    architectural shift is that RootAgentSupervisor asks the gate first and
    records the result, instead of tools being implicitly visible inside S5.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
        tools_registry=None,
    ) -> None:
        self.whitelist_builder = ToolWhitelistBuilder(capability_registry, tools_registry)
        self.data_tool_policy = DataToolVisibilityPolicy(
            capability_registry,
            tools_registry,
            whitelist_builder=self.whitelist_builder,
        )

    def visible_tools(
        self,
        state: TravelAgentState,
        *,
        phase: str,
        prompt_context: dict | None = None,
    ) -> ToolVisibility:
        projection = project_agent_core(state)
        if phase not in DATA_TOOL_PHASES:
            return ToolVisibility(
                phase=phase,
                control_tools=self._control_tools_for(phase, projection),
                required_next_actions=[f"run_{phase}"],
                decision_sources=["pipeline_gate", "control_tool_policy"],
                projection=projection,
            )
        data_decision = self.data_tool_policy.decide(
            state,
            phase=phase,
            prompt_context=prompt_context,
            projection=projection,
        )
        return ToolVisibility(
            phase=phase,
            allowed_tools=data_decision.allowed_tools,
            control_tools=self._control_tools_for(phase, projection),
            blocked_tools=data_decision.blocked_tools,
            required_next_actions=["run_evidence_phase"],
            stop_reasons=data_decision.policy_notes,
            decision_sources=["pipeline_gate", *data_decision.decision_sources],
            projection=projection,
            tool_whitelist=data_decision.tool_whitelist,
        )

    def _build_whitelist(self, state: TravelAgentState, prompt_context: dict | None) -> ToolWhitelist:
        return self.whitelist_builder.build(state, prompt_context or {})

    @staticmethod
    def _control_tools_for(phase: str, projection: dict[str, Any] | None) -> list[str]:
        projection = projection or {}
        latest = (projection.get("latest_outputs") or {}).get(phase) or {}
        phase_status = (projection.get("phase_status") or {}).get(phase)
        job_status = projection.get("job_status") or {}
        tools: list[str] = []
        if latest.get("status") == "pending_review" or phase_status == "pending_review":
            tools.append("approve_phase")
        if any(int(count or 0) > 0 for status, count in job_status.items() if status in {"queued", "running"}):
            tools.append("reconcile_job")
        if phase_status and phase_status not in {"not_started", "rolled_back"}:
            tools.append("rollback_to_phase")
        return tools
