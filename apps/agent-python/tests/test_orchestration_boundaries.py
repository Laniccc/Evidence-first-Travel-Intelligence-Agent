import re
from pathlib import Path

from app.orchestration import AgentState, StateContext, StateRuntime, TravelAgentStateMachine


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_orchestration_exports_the_single_state_runtime():
    assert TravelAgentStateMachine is not None
    assert StateRuntime is not None
    assert AgentState.HYBRID_RETRIEVE.value == "hybrid_retrieve"
    assert StateContext is not None


def test_orchestration_layer_has_no_retired_package_imports():
    retired_import = re.compile(r"^\s*(?:from|import)\s+app\.orchestrator\b", re.MULTILINE)
    offenders = [
        path.relative_to(APP_ROOT).as_posix()
        for path in (APP_ROOT / "orchestration").rglob("*.py")
        if retired_import.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
