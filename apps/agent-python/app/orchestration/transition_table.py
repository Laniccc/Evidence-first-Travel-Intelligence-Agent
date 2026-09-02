"""Static allowed transition graph for the supported Agent product scope."""

from app.orchestration.state_contracts import AgentState


ALLOWED_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.INGRESS: frozenset(
        {AgentState.CONTEXT, AgentState.SAFE_FAILURE, AgentState.FAILED}
    ),
    AgentState.CONTEXT: frozenset(
        {AgentState.UNDERSTAND, AgentState.SAFE_FAILURE, AgentState.FAILED}
    ),
    AgentState.UNDERSTAND: frozenset(
        {
            AgentState.ROUTE,
            AgentState.CLARIFICATION,
            AgentState.SAFE_FAILURE,
            AgentState.FAILED,
        }
    ),
    AgentState.ROUTE: frozenset(
        {
            AgentState.FACT_QUERY,
            AgentState.SUITABILITY,
            AgentState.COMPARISON,
            AgentState.CLARIFICATION,
            AgentState.SAFE_FAILURE,
            AgentState.FAILED,
        }
    ),
    AgentState.FACT_QUERY: frozenset(
        {AgentState.RAG_RETRIEVE, AgentState.SAFE_FAILURE, AgentState.FAILED}
    ),
    AgentState.SUITABILITY: frozenset(
        {AgentState.RAG_RETRIEVE, AgentState.SAFE_FAILURE, AgentState.FAILED}
    ),
    AgentState.COMPARISON: frozenset(
        {AgentState.RAG_RETRIEVE, AgentState.SAFE_FAILURE, AgentState.FAILED}
    ),
    AgentState.RAG_RETRIEVE: frozenset(
        {
            AgentState.EVIDENCE_EVALUATE,
            AgentState.LIVE_GAP_FILL,
            AgentState.LIMITED_ANSWER,
            AgentState.SAFE_FAILURE,
            AgentState.FAILED,
        }
    ),
    AgentState.LIVE_GAP_FILL: frozenset(
        {
            AgentState.EVIDENCE_EVALUATE,
            AgentState.LIMITED_ANSWER,
            AgentState.SAFE_FAILURE,
            AgentState.FAILED,
        }
    ),
    AgentState.EVIDENCE_EVALUATE: frozenset(
        {
            AgentState.LIVE_GAP_FILL,
            AgentState.COMPOSE,
            AgentState.LIMITED_ANSWER,
            AgentState.SAFE_FAILURE,
            AgentState.FAILED,
        }
    ),
    AgentState.COMPOSE: frozenset(
        {
            AgentState.CITATION_GUARD,
            AgentState.LIMITED_ANSWER,
            AgentState.SAFE_FAILURE,
            AgentState.FAILED,
        }
    ),
    AgentState.CITATION_GUARD: frozenset(
        {
            AgentState.DELIVER,
            AgentState.LIMITED_ANSWER,
            AgentState.SAFE_FAILURE,
            AgentState.FAILED,
        }
    ),
}


def is_allowed_transition(from_state: AgentState, to_state: AgentState) -> bool:
    return to_state in ALLOWED_TRANSITIONS.get(from_state, frozenset())
