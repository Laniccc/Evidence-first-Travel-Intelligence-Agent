"""Pytest: backend runtime + agent-python orchestrator/schemas/tools overlay."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
AGENT_APP = Path(__file__).resolve().parent / "app"

sys.path.insert(0, str(BACKEND_ROOT))

importlib.import_module("app.tools.registry")
importlib.import_module("app.tools.capability_registry")


def _overlay(module_name: str) -> None:
    rel = module_name.removeprefix("app.")
    file_path = AGENT_APP / f"{rel.replace('.', '/')}.py"
    if not file_path.is_file():
        return
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


_OVERLAY_MODULES = [
    "app.schemas.tool_whitelist",
    "app.schemas.tool_trace",
    "app.tools.gateway_config",
    "app.tools.mcp.tool_specs",
    "app.tools.mcp.client_manager",
    "app.tools.tool_name_resolver",
    "app.orchestrator.actions",
    "app.orchestrator.trace",
    "app.orchestrator.state_policy",
    "app.orchestrator.policy_guard",
    "app.orchestrator.evidence_policy_guard",
    "app.orchestrator.tool_whitelist_builder",
    "app.orchestrator.action_executor",
    "app.orchestrator.state_reducer",
    "app.orchestrator.claude_state_runner",
    "app.orchestrator.action_model_controller",
    "app.orchestrator.states.evidence_planning_and_tool_use_state",
]

for _name in _OVERLAY_MODULES:
    _overlay(_name)
