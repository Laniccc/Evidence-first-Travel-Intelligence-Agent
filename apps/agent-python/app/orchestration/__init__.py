"""Application orchestration layer for Agent runs with lazy public exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "ActionModelController": (
        "app.orchestration.action_model_controller",
        "ActionModelController",
    ),
    "AgentCoreControlTools": (
        "app.orchestration.agent_core_control_tools",
        "AgentCoreControlTools",
    ),
    "AgentCoreJobReconciler": (
        "app.orchestration.agent_core_job_reconciler",
        "AgentCoreJobReconciler",
    ),
    "AgentRun": ("app.orchestration.agent_run", "AgentRun"),
    "AgentRunService": ("app.orchestration.agent_run_service", "AgentRunService"),
    "ClarificationGate": ("app.orchestration.clarification_gate", "ClarificationGate"),
    "ClaudeStateRunner": ("app.orchestration.claude_state_runner", "ClaudeStateRunner"),
    "PipelineGate": ("app.orchestration.agent_core_pipeline_gate", "PipelineGate"),
    "RootAgentSupervisor": (
        "app.orchestration.agent_core_supervisor",
        "RootAgentSupervisor",
    ),
    "StateNodePolicy": ("app.orchestration.policies", "StateNodePolicy"),
    "StateReducer": ("app.orchestration.policies", "StateReducer"),
    "ToolVisibility": ("app.orchestration.agent_core_pipeline_gate", "ToolVisibility"),
    "S5EvidenceOrchestratorAgent": (
        "app.orchestration.s5_evidence_orchestrator",
        "S5EvidenceOrchestratorAgent",
    ),
    "S5SubagentProfile": ("app.orchestration.s5_subagent_registry", "S5SubagentProfile"),
    "TravelAgentStateMachine": ("app.orchestration.state_machine", "TravelAgentStateMachine"),
    "TravelQueryResponse": ("app.orchestration.state_machine", "TravelQueryResponse"),
    "delegate_subagent": ("app.orchestration.subagent_delegate", "delegate_subagent"),
    "subagent_definitions_for_prompt": (
        "app.orchestration.s5_subagent_registry",
        "subagent_definitions_for_prompt",
    ),
    "create_agent_run_service": (
        "app.orchestration.agent_run_service",
        "create_agent_run_service",
    ),
    "ensure_agent_core_store": (
        "app.orchestration.agent_core_store",
        "ensure_agent_core_store",
    ),
    "project_agent_core": (
        "app.orchestration.agent_core_store",
        "project_agent_core",
    ),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
