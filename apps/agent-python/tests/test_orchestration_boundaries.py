import re
from pathlib import Path

from app.orchestration import AgentRun, StateNodePolicy, StateReducer, TravelAgentStateMachine
from app.orchestration.agent_run_service import AgentRunService
from app.orchestration.states import (
    AnswerCompositionState,
    EvidencePlanningAndToolUseState,
    LLMUnderstandingState,
)
from app.orchestration.travel_agent_state import TravelAgentState


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _orchestration_python_files() -> list[Path]:
    return sorted((APP_ROOT / "orchestration").rglob("*.py"))


def test_orchestration_exports_current_runtime_surfaces():
    assert TravelAgentStateMachine is not None
    assert AgentRunService is not None
    assert StateNodePolicy is not None
    assert StateReducer is not None
    assert LLMUnderstandingState is not None
    assert EvidencePlanningAndToolUseState is not None
    assert AnswerCompositionState is not None


def test_agent_run_wraps_one_active_agent_state():
    state = TravelAgentState(
        session_id="session-1",
        query_id="query-1",
        raw_user_query="Plan a travel evidence answer",
    )

    run = AgentRun.from_state(state, user_context={"user_id": "user-1"})

    assert run.session_id == "session-1"
    assert run.query_id == "query-1"
    assert run.query == "Plan a travel evidence answer"
    assert run.user_context == {"user_id": "user-1"}
    assert run.state is state


def test_orchestration_layer_has_no_retired_static_imports():
    retired_import = re.compile(r"^\s*(?:from|import)\s+app\.orchestrator\b", re.MULTILINE)
    offenders = [
        path.relative_to(APP_ROOT).as_posix()
        for path in _orchestration_python_files()
        if retired_import.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_orchestration_layer_does_not_import_concrete_external_integrations():
    text = "\n".join(path.read_text(encoding="utf-8") for path in _orchestration_python_files())

    forbidden_imports = [
        r"^\s*(?:from|import)\s+app\.integrations\b",
        r"^\s*(?:from|import)\s+(?:app\.)?tools\.mcp\b",
        r"^\s*(?:from|import)\s+(?:httpx|requests)\b",
        r"^\s*from\s+.+\s+import\s+.*\bJavaToolGateway\b",
    ]
    assert not [pattern for pattern in forbidden_imports if re.search(pattern, text, re.MULTILINE)]
