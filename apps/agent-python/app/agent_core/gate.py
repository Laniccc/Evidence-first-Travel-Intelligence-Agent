"""Pipeline Gate — determines which tools are visible at each phase.

The Gate reads a RunProjection and returns a ToolVisibility indicating which
phase tools, control tools, and external tools are available.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agent_core.state.lifecycle import FULL_PHASE_ORDER, TERMINAL_STATUSES
from app.agent_core.state.models import BlockedTool, RunProjection, ToolVisibility

if TYPE_CHECKING:
    from app.agent_core.store import AgentCoreStore


class PipelineGate:
    """Determines tool visibility from a run projection."""

    def __init__(self, *, tools_registry=None) -> None:
        self.tools_registry = tools_registry

    def visible_tools(self, projection: RunProjection, *, topic_id: str | None = None) -> ToolVisibility:
        current_phase = projection.current_phase
        if current_phase is None:
            return ToolVisibility(
                phase_name="planning",
                topic_id=topic_id,
                allowed_phase_tools=["planning"],
                allowed_control_tools=[],
                required_next_actions=["run_planning"],
            )

        allowed_phase_tools = self._phase_tools_for(current_phase, projection)
        allowed_control_tools = self._control_tools_for(current_phase, projection)
        blocked_tools = self._blocked_tools_for(current_phase, projection)
        required_next_actions = [f"run_{current_phase}"]
        stop_reasons: list[str] = []

        if projection.status in TERMINAL_STATUSES:
            allowed_phase_tools = []
            required_next_actions = []
            stop_reasons.append(f"Run is {projection.status}")

        return ToolVisibility(
            phase_name=current_phase,
            topic_id=topic_id,
            allowed_phase_tools=allowed_phase_tools,
            allowed_control_tools=allowed_control_tools,
            blocked_tools=blocked_tools,
            required_next_actions=required_next_actions,
            stop_reasons=stop_reasons,
        )

    @staticmethod
    def _phase_tools_for(phase_name: str, _projection: RunProjection) -> list[str]:
        phase_tool_map = {
            "planning": "planning",
            "knowledge_retrieval": "knowledge_retrieval",
            "evidence_acquisition": "evidence_acquisition",
            "evidence_extraction": "evidence_extraction",
            "synthesis": "synthesis",
            "knowledge_upsert": "knowledge_upsert",
        }
        tool = phase_tool_map.get(phase_name)
        return [tool] if tool else []

    @staticmethod
    def _control_tools_for(phase_name: str, projection: RunProjection) -> list[str]:
        tools: list[str] = []
        current_cards = [pc for pc in projection.phase_cards if pc.phase_name == phase_name]
        for pc in current_cards:
            if pc.status == "pending_review":
                tools.extend(["approve_phase", "reject_artifact"])
            if pc.status in {"failed", "needs_revision"}:
                tools.append("retry_phase")
        tools.append("rollback_to_phase")
        return sorted(set(tools))

    @staticmethod
    def _blocked_tools_for(_phase_name: str, _projection: RunProjection) -> list[BlockedTool]:
        return []

    @staticmethod
    def next_phase(projection: RunProjection) -> str | None:
        current = projection.current_phase
        if current is None:
            return "planning"
        try:
            idx = FULL_PHASE_ORDER.index(current)
        except ValueError:
            return None
        if idx + 1 < len(FULL_PHASE_ORDER):
            return FULL_PHASE_ORDER[idx + 1]
        return None

    @staticmethod
    def can_advance(projection: RunProjection) -> bool:
        current = projection.current_phase
        if current is None:
            return True
        current_phases = [pc for pc in projection.phase_cards if pc.phase_name == current]
        if not current_phases:
            return True
        return all(pc.status in {"approved", "succeeded", "skipped"} for pc in current_phases)
