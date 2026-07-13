from pathlib import Path

from app.planning import (
    EvidenceGapPlanner,
    InformationNeedPlanner,
    NearbyAnchorStrategyAgent,
    PlaceResearchAgent,
    QueryPlan,
    SearchQueryRefinerAgent,
    ToolWhitelistBuilder,
)
from app.planning.research_plan import ClaimSearchPlanner, S5DomainPlanner, SearchTaskPlannerAgent
from app.understanding import (
    IntentAgent,
    ContextualQueryRewriter,
    LLMPlaceEntityExtractor,
    LLMUnderstandingSubAgent,
    QueryUnderstandingAgent,
    SemanticFrameBuilder,
    TravelTaskExtractor,
)
from app.understanding.semantic_frame import (
    NormalizedRequestToQueryUnderstanding,
    NormalizedRequestToSemanticFrame,
    NormalizedRequestToTravelTask,
    NormalizedRequestToUserGoal,
)


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _layer_text(layer_name: str) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in (APP_ROOT / layer_name).glob("*.py"))


def test_understanding_facades_export_current_capabilities():
    assert QueryUnderstandingAgent is not None
    assert LLMUnderstandingSubAgent is not None
    assert ContextualQueryRewriter is not None
    assert IntentAgent is not None
    assert TravelTaskExtractor is not None
    assert SemanticFrameBuilder is not None
    assert LLMPlaceEntityExtractor is not None
    assert NormalizedRequestToQueryUnderstanding is not None
    assert NormalizedRequestToSemanticFrame is not None
    assert NormalizedRequestToTravelTask is not None
    assert NormalizedRequestToUserGoal is not None


def test_planning_facades_export_current_capabilities():
    assert InformationNeedPlanner is not None
    assert NearbyAnchorStrategyAgent is not None
    assert PlaceResearchAgent is not None
    assert QueryPlan is not None
    assert SearchQueryRefinerAgent is not None
    assert SearchTaskPlannerAgent is not None
    assert ClaimSearchPlanner is not None
    assert S5DomainPlanner is not None
    assert ToolWhitelistBuilder is not None
    assert EvidenceGapPlanner is not None


def test_understanding_layer_has_no_tools_or_answer_composition_imports():
    text = _layer_text("understanding")

    forbidden = [
        "AnswerComposer",
        "FinalAnswerDraft",
        "answer_composer",
        "composer_agent",
        "ToolRegistry",
        "CALL_TOOL",
        "delegated_mcp_runner",
        "run_delegated_mcp",
    ]
    assert not [token for token in forbidden if token in text]


def test_planning_layer_has_no_concrete_mcp_or_http_integrations():
    text = _layer_text("planning")

    forbidden = [
        "requests",
        "httpx",
        "FastAPI",
        "McpHttpClient",
        "RestMcp",
        "run_delegated_mcp",
        "app.integrations.java_gateway",
        "tools.mcp",
    ]
    assert not [token for token in forbidden if token in text]
