"""Deprecated: agent-python no longer loads runtime from backend/."""

raise RuntimeError(
    "app._legacy is removed. Run agent-python standalone via app.main with local app.orchestrator.state_machine."
)
