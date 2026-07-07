"""Deterministic supervisor policy — task-agnostic phase transition decisions."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent_core.store import AgentCoreStore


@dataclass(frozen=True)
class SupervisorDecision:
    action: str  # "continue", "retry_gap", "limited_delivery", "block"
    reason: str = ""


class AgentCoreSupervisorPolicy:
    """Small deterministic policy for phase state → control flow."""

    def before_phase(self, store: AgentCoreStore, *, phase_name: str) -> SupervisorDecision:
        return SupervisorDecision("continue")

    def after_phase(self, store: AgentCoreStore, *, topic_id: str | None, phase_name: str) -> SupervisorDecision:
        phase = _latest_phase(store, phase_name, topic_id=topic_id)
        if phase is None:
            return SupervisorDecision("continue")
        if phase.status in {"failed", "blocked"}:
            return SupervisorDecision("limited_delivery", phase.error or f"{phase_name}:{phase.status}")
        if phase.status == "needs_revision":
            return SupervisorDecision("retry_gap", phase.error or f"{phase_name}:needs_revision")
        return SupervisorDecision("continue")


def _latest_phase(store: AgentCoreStore, phase_name: str, *, topic_id: str | None):
    phases = [
        p for p in store.list_phases(topic_id=topic_id)
        if p.phase_name == phase_name
    ]
    return phases[-1] if phases else None
