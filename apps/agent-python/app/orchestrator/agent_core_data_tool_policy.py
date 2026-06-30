"""Data-tool visibility policy used by Agent Core PipelineGate."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.capability_registry import CapabilityRegistry


DATA_TOOL_PHASES = frozenset({"research_plan", "evidence_acquisition", "evidence_review"})


class DataToolVisibilityDecision(BaseModel):
    phase: str
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[dict[str, str]] = Field(default_factory=list)
    policy_notes: list[str] = Field(default_factory=list)
    decision_sources: list[str] = Field(default_factory=list)
    tool_whitelist: ToolWhitelist | None = Field(default=None, exclude=True)


class DataToolVisibilityPolicy:
    """Resolve evidence/data tools for a phase.

    The legacy ToolWhitelistBuilder still owns detailed domain/claim/tool rules.
    This policy makes that rule engine an explicit dependency of PipelineGate,
    so Gate can also apply phase and Store-projection constraints around it.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
        tools_registry=None,
        whitelist_builder: ToolWhitelistBuilder | None = None,
    ) -> None:
        self.whitelist_builder = whitelist_builder or ToolWhitelistBuilder(
            capability_registry,
            tools_registry,
        )

    def decide(
        self,
        state: TravelAgentState,
        *,
        phase: str,
        prompt_context: dict | None = None,
        projection: dict[str, Any] | None = None,
    ) -> DataToolVisibilityDecision:
        if phase not in DATA_TOOL_PHASES:
            return DataToolVisibilityDecision(
                phase=phase,
                policy_notes=[f"data tools hidden outside data phase: {phase}"],
                decision_sources=["phase_gate"],
            )

        whitelist = self.whitelist_builder.build(state, prompt_context or {})
        notes = list(whitelist.policy_notes or [])
        notes.extend(self._projection_notes(projection))
        return DataToolVisibilityDecision(
            phase=phase,
            allowed_tools=whitelist.allowed_tool_names(),
            blocked_tools=[
                {"tool": name, "reason": whitelist.reason_by_tool.get(name, "blocked")}
                for name in whitelist.blocked_tools
            ],
            policy_notes=notes,
            decision_sources=["tool_whitelist_builder", "pipeline_gate_projection"],
            tool_whitelist=whitelist,
        )

    @staticmethod
    def _projection_notes(projection: dict[str, Any] | None) -> list[str]:
        if not projection:
            return []
        notes: list[str] = []
        current = projection.get("current_phase")
        if current:
            notes.append(f"agent_core_current_phase={current}")
        job_status = projection.get("job_status") or {}
        running = sum(int(v or 0) for k, v in job_status.items() if k in {"queued", "running"})
        if running:
            notes.append(f"agent_core_running_jobs={running}")
        return notes
