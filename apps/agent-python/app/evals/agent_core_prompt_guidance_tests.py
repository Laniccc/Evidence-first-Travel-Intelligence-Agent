from __future__ import annotations

from app.agents.s5_evidence_orchestrator_agent import S5EvidenceOrchestratorAgent
from app.orchestrator.actions import AgentActionType
from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.agent_core_prompt_guidance import agent_core_task_guidance
from app.schemas.evidence_gap_request import EvidenceGapRequest
from app.schemas.semantic_frame import DecisionType, QueryScope, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def _state(query: str, *, places: list[str], needs: list[str] | None = None) -> TravelAgentState:
    frame = SemanticFrame(
        raw_query=query,
        normalized_request=query,
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="Beijing", places=places),
        information_needs=needs or [],
    )
    return TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query=query,
        semantic_frame=frame,
    )


def test_ticket_guidance_requires_explicit_amount_and_no_login_drift():
    state = _state("\u6816\u971e\u5c71\u95e8\u7968\u4ef7\u683c\u591a\u5c11\uff1f", places=["\u6816\u971e\u5c71"])
    rules = agent_core_task_guidance(state, task_class="ticket_price_lookup")

    assert any("explicit amount" in rule for rule in rules)
    assert any("require login" in rule or "block reading" in rule for rule in rules)
    assert any("Do not invent" in rule for rule in rules)


def test_route_guardrail_action_preserves_origin_destination():
    query = "\u4ece\u5317\u4eac\u5357\u7ad9\u5230\u5929\u5b89\u95e8\u5e7f\u573a\u5750\u5730\u94c1\u600e\u4e48\u8d70\uff1f"
    state = _state(query, places=["\u5929\u5b89\u95e8\u5e7f\u573a"], needs=["route_plan"])
    agent = S5EvidenceOrchestratorAgent(llm_client=None)

    action = agent._deterministic_fallback(
        state,
        {"s5_task_class": "route_first", "max_tool_calls": 10, "tool_call_count": 0},
        step=0,
    )

    assert action.action_type == AgentActionType.CALL_SUBAGENT
    assert action.target == "route_feasibility_agent"
    params = action.arguments["tool_parameters"]
    assert params["origin"] == "\u5317\u4eac\u5357\u7ad9"
    assert params["destination"] == "\u5929\u5b89\u95e8\u5e7f\u573a"
    assert params["mode"] == "transit"


def test_geo_guardrail_stays_on_numeric_fact_search():
    state = _state("\u9ec4\u5c71\u4e3b\u5cf0\u6d77\u62d4\u591a\u5c11\u7c73\uff1f", places=["\u9ec4\u5c71"], needs=["elevation"])
    agent = S5EvidenceOrchestratorAgent(llm_client=None)

    action = agent._deterministic_fallback(
        state,
        {"s5_task_class": "geo_fact_lookup", "max_tool_calls": 10, "tool_call_count": 0},
        step=0,
    )

    assert action.action_type == AgentActionType.CALL_SUBAGENT
    assert action.target == "fact_search_agent"
    assert action.arguments["claim_target"] == "elevation"
    assert "\u6d77\u62d4" in action.arguments["search_query"]


def test_gap_filling_max_steps_limits_tools_and_template_searches():
    state = _state("\u6816\u971e\u5c71\u95e8\u7968\u4ef7\u683c\u591a\u5c11\uff1f", places=["\u6816\u971e\u5c71"], needs=["ticket_price"])
    gap = EvidenceGapRequest(
        claim_type="ticket_price",
        suggested_tools=["search_mcp"],
        query_templates=[
            "\u6816\u971e\u5c71 \u95e8\u7968 \u4ef7\u683c",
            "\u6816\u971e\u5c71 \u552e\u7968 \u5b98\u65b9",
        ],
        max_extra_steps=1,
    )
    controller = ActionModelController(llm_client=None)
    prompt_context = {
        "gap_request": gap.model_dump(),
        "gap_max_extra_steps": 1,
        "allowed_tools": [{"name": "search_mcp"}],
    }

    first = controller._plan_gap_filling(state, prompt_context, step=0)
    second = controller._plan_gap_filling(state, prompt_context, step=1)

    assert first.action_type == AgentActionType.CALL_TOOL
    assert first.target == "search_mcp"
    assert second.action_type == AgentActionType.FINISH_STATE


def test_poi_task_budget_finishes_before_long_tail_loop():
    state = _state("\u5317\u4eac\u6545\u5bab\u9644\u8fd1\u6709\u4ec0\u4e48\u597d\u5403\u7684\uff1f", places=["\u6545\u5bab"], needs=["nearby_food"])
    agent = S5EvidenceOrchestratorAgent(llm_client=None)

    action = agent._deterministic_fallback(
        state,
        {"s5_task_class": "poi_recommendation", "max_tool_calls": 20, "tool_call_count": 0},
        step=8,
    )

    assert action.action_type == AgentActionType.FINISH_STATE


def test_generic_nearby_food_list_does_not_force_review_crawler():
    from app.orchestrator.nearby_enrichment_policy import requires_nearby_reputation_signal

    generic = _state(
        "\u5317\u4eac\u6545\u5bab\u9644\u8fd1\u6709\u4ec0\u4e48\u597d\u5403\u7684\uff1f",
        places=["\u6545\u5bab"],
        needs=["nearby_food"],
    )
    reputation = _state(
        "\u6545\u5bab\u9644\u8fd1\u54ea\u5bb6\u9910\u5385\u53e3\u7891\u597d\uff1f",
        places=["\u6545\u5bab"],
        needs=["nearby_food"],
    )

    assert requires_nearby_reputation_signal(generic) is False
    assert requires_nearby_reputation_signal(reputation) is True
