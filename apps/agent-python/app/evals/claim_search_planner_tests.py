"""Tests for claim-targeted search planning."""

from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.semantic_frame import SemanticEntities, SemanticFrame, QueryScope, TaskFamily, DecisionType, TimeScope
from app.schemas.user_query import TravelAgentState


def _duku_frame(**kwargs) -> SemanticFrame:
    base = dict(
        raw_query="新疆的独库公路每年几月份开放？",
        normalized_request="新疆独库公路开放月份",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.BEST_TIME_TO_VISIT,
        entities=SemanticEntities(country="China", region="新疆", places=["独库公路"]),
        time_scope=TimeScope.SEASONAL,
        information_needs=["best_time_to_visit"],
    )
    base.update(kwargs)
    return SemanticFrame(**base)


def test_claim_search_planner_builds_targeted_queries():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    queries = ClaimSearchPlanner.build_queries(state)
    assert len(queries) >= 3
    assert any("独库公路" in q for q in queries)
    assert any("通车" in q or "开放" in q for q in queries)
    assert any("新疆" in q for q in queries)


def test_claim_search_planner_short_queries_first():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    queries = ClaimSearchPlanner.build_queries(state)
    assert queries[0] == "独库公路什么时候开放"
    assert ClaimSearchPlanner.max_search_attempts(state) == 6


def test_refine_queries_skips_already_tried():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    seed = ClaimSearchPlanner.build_queries(state)
    refined = ClaimSearchPlanner.refine_queries_after_misses(state, set(seed))
    assert all(q not in seed for q in refined)
    assert any("独库公路开放时间" == q for q in refined)


def test_contract_whitelist_allows_knowledge_prior_for_optional_context():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    wl = ToolWhitelistBuilder().build(state)
    assert "knowledge_prior" in wl.allowed_tool_names()
