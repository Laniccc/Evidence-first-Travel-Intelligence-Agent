from app.orchestration.states.llm_understanding import UnderstandingHandler
from app.orchestration.states.retrieval_planning import RetrievalPlanningHandler
from app.orchestration.states.routing import RouteHandler


def test_product_capabilities_map_to_explicit_state_handlers():
    assert UnderstandingHandler is not None
    assert RouteHandler is not None
    assert RetrievalPlanningHandler is not None
