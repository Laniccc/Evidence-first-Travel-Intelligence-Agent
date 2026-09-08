import asyncio
from types import SimpleNamespace

import pytest

from app.orchestration.langgraph_runtime import LangGraphRuntime
from app.orchestration.state_runtime import StateRuntime
from app.orchestration.state_machine import TravelAgentStateMachine
from app.orchestration.state_audit import InMemoryStateAuditStore
from app.orchestration.state_contracts import AgentState, StateResult, StatePolicy, TERMINAL_STATES
from app.orchestration.transition_table import ALLOWED_TRANSITIONS
from tests.test_state_runtime import HandlerReturning, TimeoutOnceHandler, context_for
from tests.fakes.failing_retrievers import chunk, report


def test_default_graph_compiles_with_independent_business_nodes_and_table_edges():
    machine = TravelAgentStateMachine()
    assert isinstance(machine._runtime, LangGraphRuntime)
    graph = machine._runtime.graph.get_graph()
    assert {s.value for s in AgentState if s not in TERMINAL_STATES} <= set(graph.nodes)
    edges = {(e.source, e.target) for e in graph.edges}
    for source, destinations in ALLOWED_TRANSITIONS.items():
        for destination in destinations:
            target = "__end__" if destination in TERMINAL_STATES else destination.value
            assert (source.value, target) in edges
    assert isinstance(TravelAgentStateMachine(orchestration_engine="legacy")._runtime, StateRuntime)
    with pytest.raises(ValueError):
        TravelAgentStateMachine(orchestration_engine="unknown")


class Facts:
    async def aretrieve(self, plan):
        return report(plan, hits=[chunk(f"{plan.attraction_ids[0]}-{fact.value}", "景点有效事实",
            fact_type=fact.value, attraction_id=plan.attraction_ids[0]) for fact in plan.fact_types])


CATALOG = [SimpleNamespace(name="故宫", attraction_id="forbidden-city", city="北京"),
           SimpleNamespace(name="颐和园", attraction_id="summer-palace", city="北京")]


@pytest.mark.parametrize("query,branch", [
    ("故宫几点开放", "fact_query"), ("故宫适合老人吗", "suitability"), ("故宫和颐和园哪个适合老人", "comparison")])
async def test_real_handlers_route_through_guard_before_delivery(query, branch):
    responses = []
    for engine in ("legacy", "langgraph"):
        machine = TravelAgentStateMachine(orchestration_engine=engine, retriever=Facts(),
            attraction_matcher=lambda text: [a for a in CATALOG if a.name in text],
            attraction_resolver=lambda name: next(a.attraction_id for a in CATALOG if a.name == name))
        response = await machine.run(query)
        summary = response.orchestration_summary
        path = [e["state"] for e in summary["state_audit"] if e["event_type"] == "transition_committed"]
        assert path == ["ingress", "context", "understand", "route", branch, "retrieval_plan",
                        "hybrid_retrieve", "evidence_evaluate", "compose", "citation_guard"]
        assert summary["terminal_state"] == "deliver" and response.citation_report["passed"]
        responses.append(response)
    assert responses[0].answer == responses[1].answer
    assert set(responses[0].model_dump()) == set(responses[1].model_dump())


@pytest.mark.parametrize("query,terminal", [("", "safe_failure"), ("帮我安排三天行程", "clarification"),
                                          ("故宫几点开放", "safe_failure")])
async def test_real_terminal_and_missing_rag_paths(query, terminal):
    machine = TravelAgentStateMachine(
        attraction_matcher=lambda text: [a for a in CATALOG if a.name in text],
        attraction_resolver=lambda _: "forbidden-city")
    response = await machine.run(query)
    assert response.orchestration_summary["terminal_state"] == terminal
    path = [e["state"] for e in response.orchestration_summary["state_audit"] if e["event_type"] == "phase_started"]
    if query == "故宫几点开放":
        assert path.count("live_gap_fill") == 1 and "evidence_evaluate" in path
        assert "compose" not in path


@pytest.mark.parametrize("engine", [StateRuntime, LangGraphRuntime])
async def test_shared_timeout_recovery_and_original_context_identity(engine):
    ctx, audit, handler = context_for(), InMemoryStateAuditStore(), TimeoutOnceHandler()
    seen = []
    class Last:
        async def run(self, context):
            seen.append(context)
            assert context.current_state == AgentState.CONTEXT and "ingress" in context.artifacts
            return StateResult.succeeded(next_state=AgentState.SAFE_FAILURE)
    runtime = engine(handlers={AgentState.INGRESS: handler, AgentState.CONTEXT: Last()},
                     audit=audit, policies={AgentState.INGRESS: StatePolicy(timeout_seconds=0.01, max_attempts=2)})
    result = await runtime.run(ctx)
    assert result.context is ctx and seen == [ctx] and handler.calls == 2
    assert result.terminal_state == AgentState.SAFE_FAILURE and result.steps == 2
    assert [e.event_type for e in audit.events] == ["phase_started", "phase_failed", "phase_started",
        "phase_recovered", "transition_committed", "phase_started", "phase_succeeded", "transition_committed"]


@pytest.mark.parametrize("engine", [StateRuntime, LangGraphRuntime])
async def test_illegal_transition_does_not_execute_target_or_commit_artifact(engine):
    ctx, audit = context_for(), InMemoryStateAuditStore()
    target = HandlerReturning(StateResult.succeeded(next_state=AgentState.CITATION_GUARD))
    runtime = engine(handlers={AgentState.INGRESS: HandlerReturning(
        StateResult.succeeded(next_state=AgentState.COMPOSE, output={"unsafe": True})),
        AgentState.COMPOSE: target}, audit=audit)
    result = await runtime.run(ctx)
    assert result.failure.code == "illegal_transition" and result.terminal_state == AgentState.FAILED
    assert target.calls == 0 and not ctx.artifacts and ctx.current_state == AgentState.INGRESS
    assert [e.event_type for e in audit.events] == ["phase_started", "phase_succeeded", "phase_failed"]


@pytest.mark.parametrize("engine", [StateRuntime, LangGraphRuntime])
async def test_budget_missing_handler_and_terminal_entry_match_legacy(engine):
    for limit, code in [(0, "max_steps_exceeded"), (24, "missing_state_handler")]:
        ctx = context_for()
        result = await engine(handlers={}, audit=InMemoryStateAuditStore(), max_steps=limit).run(ctx)
        assert result.failure.code == code and result.steps == 0
    for terminal in TERMINAL_STATES:
        ctx = context_for()
        ctx.current_state = terminal
        result = await engine(handlers={}, audit=InMemoryStateAuditStore(), max_steps=0).run(ctx)
        assert result.terminal_state == terminal and result.steps == 0 and result.context is ctx


async def test_graph_cancellation_propagates_without_next_node():
    started, cancelled = asyncio.Event(), asyncio.Event()
    class Slow:
        async def run(self, context):
            started.set()
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()
    audit = InMemoryStateAuditStore()
    runtime = LangGraphRuntime(handlers={AgentState.INGRESS: Slow()}, audit=audit)
    task = asyncio.create_task(runtime.run(context_for()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set() and [e.event_type for e in audit.events] == ["phase_started"]


@pytest.mark.parametrize("engine", [StateRuntime, LangGraphRuntime])
async def test_legal_cycle_hits_business_budget_before_graph_recursion_error(engine):
    audit, ctx = InMemoryStateAuditStore(), context_for()
    ctx.current_state = AgentState.EVIDENCE_EVALUATE
    runtime = engine(handlers={
        AgentState.EVIDENCE_EVALUATE: HandlerReturning(StateResult.succeeded(next_state=AgentState.LIVE_GAP_FILL)),
        AgentState.LIVE_GAP_FILL: HandlerReturning(StateResult.succeeded(next_state=AgentState.EVIDENCE_EVALUATE)),
    }, audit=audit, max_steps=3)
    result = await runtime.run(ctx)
    assert result.steps == 3 and result.failure.code == "max_steps_exceeded"
    assert len([e for e in audit.events if e.event_type == "transition_committed"]) == 3
    assert audit.events[-1].failure.code == "max_steps_exceeded"


@pytest.mark.parametrize("engine", [StateRuntime, LangGraphRuntime])
async def test_unhandled_failure_does_not_retry_or_double_audit(engine):
    class Broken:
        calls = 0
        async def run(self, context):
            self.calls += 1
            raise RuntimeError("secret")
    handler, audit = Broken(), InMemoryStateAuditStore()
    result = await engine(handlers={AgentState.INGRESS: handler}, audit=audit,
                         policies={AgentState.INGRESS: StatePolicy(max_attempts=3)}).run(context_for())
    assert result.failure.code == "unhandled_state_error" and handler.calls == 1
    assert result.terminal_state == AgentState.FAILED
    assert [e.event_type for e in audit.events] == ["phase_started", "phase_failed"]
    assert "secret" not in result.failure.model_dump_json()


@pytest.mark.parametrize("engine", ["langgraph", "legacy"])
async def test_factory_engine_selection_and_real_promotion_branch(tmp_path, engine):
    from app.config import Settings
    from app.contracts.request import AgentQueryRequest
    from app.main import build_runtime
    from tests.integration.test_online_runtime_wiring import settings, seed, transport, parameters
    assert Settings(_env_file=None).orchestration_engine == "langgraph"
    config = settings(tmp_path, orchestration_engine=engine)
    seed(config)
    service, _, resources = build_runtime(config, llm_http_client=transport([]), mcp_parameters=parameters())
    assert isinstance(service._state_machine._runtime, LangGraphRuntime if engine == "langgraph" else StateRuntime)
    await resources.start()
    try:
        response = await service.query(AgentQueryRequest(query="颐和园地址"))
        path = [e["state"] for e in response.orchestration_summary["state_audit"] if e["event_type"] == "transition_committed"]
        assert path[-5:] == ["live_gap_fill", "evidence_evaluate", "knowledge_promote", "compose", "citation_guard"]
        assert response.orchestration_summary["terminal_state"] == "deliver"
        assert response.citation_report["passed"] and response.promotion_summary.status == "published"
    finally:
        await resources.aclose()
