from types import SimpleNamespace
import json

import pytest

from app.orchestrator.agent_core_research_plan import build_research_plan
from app.orchestrator.agent_core_store import (
    AgentCoreStore,
    JsonlAgentStore,
    SQLiteAgentStore,
    ensure_agent_core_store,
    project_agent_core,
)
from app.orchestrator.agent_core_supervisor import RootAgentSupervisor
from app.orchestrator.agent_core_control_tools import AgentCoreControlTools
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.tool_whitelist import ToolDescriptor, ToolWhitelist
from app.schemas.evidence_decision_report import ClaimDecision, EvidenceDecisionReport
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.user_query import TravelAgentState


def test_agent_core_sidecar_projects_minimal_pipeline():
    state = TravelAgentState(session_id="s", query_id="run-1", raw_user_query="夫子庙需要收费吗")
    TravelAgentStateMachine._agent_core_init_run(state, {"debug": True})
    state.evidence = [
        Evidence(
            evidence_id="ev-1",
            source_name="Fliggy FlyAI",
            source_type=SourceType.TICKET_PLATFORM,
            source_url="https://a.feizhu.com/demo",
            country="China",
            city="南京",
            place_name="夫子庙",
            confidence=0.62,
            claims=[
                Claim(claim_type=ClaimType.TICKET_PRICE_CANDIDATE, value="¥29", confidence=0.62),
                Claim(claim_type=ClaimType.TICKET_TYPE, value="夫子庙大成殿 - 大门票 成人票", confidence=0.55),
            ],
        )
    ]
    state.evidence_decision_report = EvidenceDecisionReport(
        claim_decisions=[
            ClaimDecision(
                claim_type="ticket_price",
                adoption="adopt_with_limitation",
                coverage_quality="partial",
                adoption_level="partial",
                adopted_evidence_ids=["ev-1"],
            )
        ]
    )
    state.structured_result = {"completed_search_task_ids": ["search-1"]}

    TravelAgentStateMachine._agent_core_record_evidence_pipeline(state)
    state.final_response = "夫子庙开放区域不能据此认定整体收费。"
    TravelAgentStateMachine._agent_core_record_answer_draft(state, {"compose_mode": "fact_lookup_guided"})
    TravelAgentStateMachine._agent_core_record_citation_guard(state, 0.7)
    TravelAgentStateMachine._agent_core_record_delivery(state, 0.7)

    projection = project_agent_core(state)

    assert projection is not None
    assert projection["run_id"] == "run-1"
    assert projection["phase_status"]["ingress"] == "succeeded"
    assert projection["phase_status"]["answer_draft"] == "approved"
    assert projection["phase_status"]["citation_guard"] == "approved"
    assert projection["phase_status"]["delivery"] == "succeeded"
    assert projection["latest_outputs"]["answer_draft"]["status"] == "approved"
    assert projection["latest_outputs"]["citation_guard"]["status"] == "approved"
    assert projection["latest_artifacts"]["answer"]["status"] == "approved"
    assert projection["evidence_summary"]["count"] == 1
    assert projection["evidence_summary"]["usage_role_counts"]["answerable"] == 1
    assert projection["evidence_summary"]["strength_counts"]["partial"] == 1
    assert projection["evidence_summary"]["adopted_evidence_count"] == 1
    assert projection["evidence_summary"]["effective_query_count"] == 1
    assert projection["latest_artifacts"]["final_answer"]["status"] == "succeeded"


def test_agent_core_store_is_excluded_from_travel_state_dump():
    state = TravelAgentState(session_id="s", query_id="run-2", raw_user_query="test")
    ensure_agent_core_store(state)

    dumped = state.model_dump()

    assert "agent_core_store" not in dumped


def test_agent_core_store_protocol_exposes_projection_queries():
    state = TravelAgentState(session_id="s", query_id="run-store-protocol", raw_user_query="test")
    store = ensure_agent_core_store(state)
    output = store.add_phase_output("research_plan", kind="research_plan", status="pending_review")

    assert isinstance(store, AgentCoreStore)
    assert store.has_phase_output("research_plan", kind="research_plan")
    assert store.latest_phase_output("research_plan", status="pending_review").id == output.id


def test_jsonl_agent_store_persists_append_only_records(tmp_path):
    path = tmp_path / "agent_core.jsonl"
    store = JsonlAgentStore(run_id="run-jsonl", path=path)
    output = store.add_phase_output("research_plan", kind="research_plan", status="pending_review")
    store.approve_phase("research_plan", output_id=output.id, approved_by="tester")
    job = store.add_job(tool_name="browser_mcp", status="running")
    store.update_job(job.id, status="succeeded")

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    event_types = [row["event_type"] for row in rows]

    assert "phase_state" in event_types
    assert "phase_output" in event_types
    assert "phase_approval" in event_types
    assert "job" in event_types
    assert "job_update" in event_types
    assert store.project().job_status["succeeded"] == 1


def test_sqlite_agent_store_persists_queryable_events(tmp_path):
    path = tmp_path / "agent_core.sqlite3"
    store = SQLiteAgentStore(run_id="run-sqlite", path=path)
    output = store.add_phase_output("research_plan", kind="research_plan", status="pending_review")
    store.approve_phase("research_plan", output_id=output.id, approved_by="tester")
    job = store.add_job(tool_name="browser_mcp", status="running")
    store.update_job(job.id, status="succeeded")

    events = store.events()
    event_types = [row["event_type"] for row in events]

    assert path.exists()
    assert "phase_output" in event_types
    assert "phase_approval" in event_types
    assert "job_update" in event_types
    assert store.project().phase_status["research_plan"] == "approved"


def test_to_response_embeds_agent_core_projection_without_changing_api_schema():
    state = TravelAgentState(session_id="s", query_id="run-3", raw_user_query="test")
    state.final_response = "ok"
    TravelAgentStateMachine._agent_core_init_run(state, None)

    sm = TravelAgentStateMachine.__new__(TravelAgentStateMachine)
    sm.tools = SimpleNamespace(traces=[])

    response = sm._to_response(state, 0.8)

    assert response.answer == "ok"
    assert response.orchestration_summary is not None
    projection = response.orchestration_summary["agent_core_projection"]
    assert projection["run_id"] == "run-3"
    assert projection["phase_status"]["delivery"] == "succeeded"


@pytest.mark.asyncio
async def test_root_agent_supervisor_drives_phase_surface_and_gate():
    class FakeRuntime:
        def __init__(self):
            self.tools = SimpleNamespace(traces=[], clear_traces=lambda: None)
            self.capability_registry = None

        def _build_conversation_context(self, query, user_context, session_id):
            from app.schemas.conversation_memory import ConversationMemory
            from app.schemas.user_query import UserContext

            state = TravelAgentState(session_id=session_id or "s", query_id="run-4", raw_user_query=query)
            TravelAgentStateMachine._agent_core_init_run(state, user_context)
            return UserContext(), ConversationMemory(), state

        async def _run_query_understanding(self, state, ctx, user_context):
            state.semantic_frame = None
            return state

        def _derive_intent_profile(self, state):
            return state

        def _run_answer_mode_routing(self, state):
            TravelAgentStateMachine._agent_core_record_input_contract(state)
            return state

        def _dispatch_from_contract(self, state):
            raise AssertionError("legacy dispatch should not be called by RootAgentSupervisor")

        async def _dispatch_by_answer_mode(self, state):
            raise AssertionError("legacy answer-mode dispatch should not be called by RootAgentSupervisor")

        def _apply_region_gate(self, state, query, gate_query, memory):
            return None

        async def _resolve_user_goal(self, state, ctx, gate_query):
            from app.schemas.user_query import UserGoal

            return UserGoal(place_candidates=["测试地"])

        def _complete_context(self, state, ctx):
            return None

        def _resolve_target_label(self, state):
            return "测试地"

        def _place_context_for(self, state, place, index):
            return None

        async def _run_evidence_loop(self, state, *, place_name, place_context, reset_evidence=True):
            TravelAgentStateMachine._agent_core_record_evidence_pipeline(state)
            return state

        def _resolve_compose_mode(self, state):
            return "advisory"

        async def _run_answer_composition(self, state, **compose_kwargs):
            state.final_response = "ok"
            TravelAgentStateMachine._agent_core_record_answer_draft(state, compose_kwargs)
            return state

        def _citation_check(self, state, fact_sheets, review_results, base_confidence):
            TravelAgentStateMachine._agent_core_record_citation_guard(state, base_confidence)
            return base_confidence

        def _to_response(self, state, confidence):
            TravelAgentStateMachine._agent_core_record_delivery(state, confidence)
            projection = project_agent_core(state)
            from app.schemas.response import StructuredResult, TravelQueryResponse

            return TravelQueryResponse(
                answer=state.final_response or "",
                structured_result=StructuredResult(),
                confidence=confidence,
                orchestration_summary={"agent_core_projection": projection},
            )

    response = await RootAgentSupervisor(FakeRuntime()).run(
        query="测试",
        user_context=None,
        session_id="s",
    )

    projection = response.orchestration_summary["agent_core_projection"]
    assert response.answer == "ok"
    assert projection["phase_status"]["input_contract"] in {"draft", "succeeded"}
    assert projection["phase_status"]["research_plan"] == "approved"
    assert projection["phase_status"]["evidence_acquisition"] == "succeeded"
    assert projection["latest_outputs"]["research_plan"]["kind"] == "research_plan"
    assert projection["latest_artifacts"]["research_plan"]["payload"]["task_class"]


def test_control_tools_approve_phase_updates_output_and_artifact():
    state = TravelAgentState(session_id="s", query_id="run-control-1", raw_user_query="test")
    store = ensure_agent_core_store(state)
    artifact = store.add_artifact(
        artifact_type="answer",
        status="pending_review",
        payload={"answer": "draft"},
    )
    output = store.add_phase_output(
        "answer_draft",
        kind="answer_artifact",
        status="pending_review",
        payload={"artifact_id": artifact.id},
    )

    result = AgentCoreControlTools().approve_phase(
        state,
        phase="answer_draft",
        output_id=output.id,
        approved_by="tester",
    )

    projection = result.projection
    assert result.status == "succeeded"
    assert projection["phase_status"]["answer_draft"] == "approved"
    assert projection["latest_outputs"]["answer_draft"]["status"] == "approved"
    assert projection["latest_artifacts"]["answer"]["status"] == "approved"


def test_control_tools_rollback_to_phase_marks_later_phases():
    state = TravelAgentState(session_id="s", query_id="run-control-2", raw_user_query="test")
    store = ensure_agent_core_store(state)
    store.add_phase_output("research_plan", kind="research_plan", status="succeeded")
    store.add_phase_output("evidence_acquisition", kind="evidence_batch", status="succeeded")
    store.add_phase_output("answer_draft", kind="answer_artifact", status="succeeded")

    result = AgentCoreControlTools().rollback_to_phase(
        state,
        phase="evidence_acquisition",
        reason="ticket evidence was unsupported",
    )

    projection = result.projection
    assert result.status == "succeeded"
    assert projection["phase_status"]["evidence_acquisition"] == "running"
    assert projection["phase_status"]["answer_draft"] == "rolled_back"


def test_control_tools_reconcile_job_updates_store_projection():
    state = TravelAgentState(session_id="s", query_id="run-control-3", raw_user_query="test")
    store = ensure_agent_core_store(state)
    job = store.add_job(tool_name="official_page_reader_mcp", status="running")

    result = AgentCoreControlTools().reconcile_job(
        state,
        job_id=job.id,
        status="succeeded",
        output_ref="artifact-1",
    )

    assert result.status == "succeeded"
    assert result.job_id == job.id
    assert result.projection["job_status"]["succeeded"] == 1
    assert store.job_records[job.id].output_ref == "artifact-1"


def test_job_reconciler_updates_pending_jobs_through_control_tool():
    from app.orchestrator.agent_core_job_reconciler import AgentCoreJobReconciler

    state = TravelAgentState(session_id="s", query_id="run-reconcile-1", raw_user_query="test")
    store = ensure_agent_core_store(state)
    job = store.add_job(tool_name="browser_mcp", status="running")

    reconciler = AgentCoreJobReconciler(
        resolver=lambda row: {"status": "succeeded", "output_ref": f"out-{row.id}"}
    )
    results = reconciler.reconcile_pending(state)

    assert len(results) == 1
    assert results[0].status == "succeeded"
    assert store.job_records[job.id].status == "succeeded"
    assert store.job_records[job.id].output_ref == f"out-{job.id}"


def test_job_reconciler_registry_resolves_by_tool_name():
    from app.orchestrator.agent_core_job_reconciler import (
        AgentCoreJobReconciler,
        AgentCoreJobResolverRegistry,
    )

    state = TravelAgentState(session_id="s", query_id="run-reconcile-2", raw_user_query="test")
    store = ensure_agent_core_store(state)
    browser_job = store.add_job(tool_name="browser_mcp", status="running")
    store.add_job(tool_name="search_mcp", status="running")
    registry = AgentCoreJobResolverRegistry()
    registry.register(
        "browser_mcp",
        lambda row: {"status": "succeeded", "output_ref": f"browser-{row.id}"},
    )

    results = AgentCoreJobReconciler(registry=registry).reconcile_pending(state)

    assert len(results) == 1
    assert results[0].job_id == browser_job.id
    assert store.job_records[browser_job.id].status == "succeeded"
    assert store.project().job_status["running"] == 1


def test_pipeline_gate_exposes_control_tools_separately_from_data_tools():
    from app.orchestrator.agent_core_pipeline_gate import PipelineGate

    state = TravelAgentState(session_id="s", query_id="run-control-4", raw_user_query="test")
    store = ensure_agent_core_store(state)
    store.add_phase_output("answer_draft", kind="answer_artifact", status="pending_review")
    store.add_job(tool_name="browser_mcp", status="running")

    visibility = PipelineGate().visible_tools(state, phase="answer_draft")

    assert visibility.allowed_tools == []
    assert "approve_phase" in visibility.control_tools
    assert "reconcile_job" in visibility.control_tools
    assert "rollback_to_phase" in visibility.control_tools
    assert "control_tool_policy" in visibility.decision_sources


def test_pipeline_gate_routes_data_tool_decision_through_policy():
    from app.orchestrator.agent_core_pipeline_gate import PipelineGate

    state = TravelAgentState(session_id="s", query_id="run-control-5", raw_user_query="test")
    gate = PipelineGate()
    visibility = gate.visible_tools(state, phase="evidence_acquisition")

    assert "pipeline_gate" in visibility.decision_sources
    assert "tool_whitelist_builder" in visibility.decision_sources
    assert visibility.tool_whitelist is not None


def test_debug_formatter_renders_agent_core_projection():
    from app.debug_session_log import _format_agent_core_projection

    lines = _format_agent_core_projection(
        {
            "agent_core_projection": {
                "run_id": "run-debug",
                "current_phase": "evidence_acquisition",
                "phase_status": {
                    "research_plan": "approved",
                    "evidence_acquisition": "running",
                },
                "latest_outputs": {
                    "research_plan": {
                        "kind": "research_plan",
                        "status": "approved",
                    }
                },
                "latest_artifacts": {
                    "research_plan": {
                        "payload": {
                            "task_class": "ticket_price_lookup",
                            "allowed_tools": ["search_mcp"],
                            "claim_plans": [
                                {
                                    "claim_type": "ticket_price",
                                    "priority": "required",
                                    "sequence_key": "ticket_price_lookup",
                                    "must_attempt": ["search_mcp"],
                                }
                            ],
                        }
                    }
                },
                "evidence_summary": {
                    "count": 2,
                    "source_type_counts": {"official": 1},
                    "usage_role_counts": {"answerable": 1, "rejected": 1},
                    "strength_counts": {"strong": 1, "rejected": 1},
                    "effective_query_count": 1,
                    "adopted_evidence_count": 1,
                    "rejected_evidence_count": 1,
                },
                "job_status": {"running": 1},
            }
        }
    )
    text = "\n".join(lines)

    assert "run-debug" in text
    assert "ticket_price_lookup" in text
    assert "ticket_price" in text
    assert "search_mcp" in text
    assert "Evidence records" in text
    assert "Effective query count" in text
    assert "Usage role counts" in text


def test_research_plan_preserves_multi_claim_contract_and_tool_sequences():
    state = TravelAgentState(session_id="s", query_id="run-4b", raw_user_query="price and hours")
    state.response_contract = ResponseContract(
        user_goal_summary="Find ticket price and opening hours",
        claim_requirements=[
            ClaimRequirement(
                claim_type="ticket_price",
                priority="required",
                requires_exact_fact=True,
                preferred_tools=["official_page_reader_mcp"],
                forbidden_tools=["knowledge_prior"],
                model_prior_allowed=False,
            ),
            ClaimRequirement(
                claim_type="opening_hours",
                priority="important",
                requires_live_data=True,
                preferred_tools=["official_source_discovery_mcp"],
            ),
        ],
    )
    whitelist = ToolWhitelist(
        state_name="evidence_planning_and_tool_use",
        allowed_tools=[
            ToolDescriptor(name="official_page_reader_mcp", description="official", configured=True),
            ToolDescriptor(name="search_mcp", description="search", configured=True),
        ],
        blocked_tools=["knowledge_prior"],
        reason_by_tool={"knowledge_prior": "forbidden_by_contract"},
    )
    from app.orchestrator.agent_core_pipeline_gate import ToolVisibility

    plan = build_research_plan(
        state,
        visibility=ToolVisibility(
            phase="research_plan",
            allowed_tools=whitelist.allowed_tool_names(),
            blocked_tools=[{"tool": "knowledge_prior", "reason": "forbidden_by_contract"}],
            tool_whitelist=whitelist,
        ),
    )

    assert [claim.claim_type for claim in plan.claim_plans] == ["ticket_price", "opening_hours"]
    assert plan.claim_plans[0].priority == "required"
    assert "official_page_reader_mcp" in plan.claim_plans[0].tool_sequence
    assert plan.claim_plans[1].requires_live_data is True
    assert plan.allowed_tools == ["official_page_reader_mcp", "search_mcp"]


@pytest.mark.asyncio
async def test_evidence_planning_state_consumes_pipeline_gate(monkeypatch):
    from app.orchestrator.agent_core_pipeline_gate import ToolVisibility
    from app.orchestrator.states import evidence_planning_and_tool_use_state as s5_module
    from app.orchestrator.states.evidence_planning_and_tool_use_state import EvidencePlanningAndToolUseState

    class FakeSettings:
        mcp_enabled = False
        mcp_http_autostart = False
        mcp_max_tool_calls_per_state = 4

    class FakeGate:
        def __init__(self):
            self.called = False

        def visible_tools(self, state, *, phase, prompt_context=None):
            self.called = True
            whitelist = ToolWhitelist(
                state_name="evidence_planning_and_tool_use",
                allowed_tools=[
                    ToolDescriptor(name="search_mcp", description="search", configured=True)
                ],
                blocked_tools=["knowledge_prior"],
                reason_by_tool={"knowledge_prior": "forbidden_by_gate"},
                policy_notes=["from PipelineGate"],
            )
            return ToolVisibility(
                phase=phase,
                allowed_tools=["search_mcp"],
                blocked_tools=[{"tool": "knowledge_prior", "reason": "forbidden_by_gate"}],
                required_next_actions=["run_evidence_phase"],
                stop_reasons=["from PipelineGate"],
                tool_whitelist=whitelist,
            )

    class FakeRunner:
        async def run(self, state, policy, prompt_context):
            state.structured_result = {
                "s5_allowed_tools_seen": [t["name"] for t in prompt_context["allowed_tools"]],
                "s5_policy_notes_seen": list(prompt_context["tool_whitelist"].policy_notes),
            }
            state.evidence_planning_completed = True
            return state

    monkeypatch.setattr(s5_module, "get_settings", lambda: FakeSettings())
    gate = FakeGate()
    s5 = EvidencePlanningAndToolUseState.__new__(EvidencePlanningAndToolUseState)
    s5.pipeline_gate = gate
    s5.runner = FakeRunner()
    s5.tools = None
    s5.tool_router = None

    state = TravelAgentState(session_id="s", query_id="run-5", raw_user_query="test")
    out = await s5.run(state, reset_evidence=False)

    assert gate.called
    assert out.structured_result["s5_allowed_tools_seen"] == ["search_mcp"]
    assert out.structured_result["s5_policy_notes_seen"] == ["from PipelineGate"]


def test_s5_prompt_context_consumes_agent_core_research_plan():
    from app.orchestrator.states.evidence_planning_and_tool_use_state import EvidencePlanningAndToolUseState

    state = TravelAgentState(session_id="s", query_id="run-6", raw_user_query="test")
    store = ensure_agent_core_store(state)
    store.add_artifact(
        artifact_type="research_plan",
        status="approved",
        payload={
            "task_class": "ticket_price_lookup",
            "claim_plans": [{"claim_type": "ticket_price", "must_attempt": ["search_mcp"]}],
        },
    )
    whitelist = ToolWhitelist(
        state_name="evidence_planning_and_tool_use",
        allowed_tools=[ToolDescriptor(name="search_mcp", description="search", configured=True)],
    )
    s5 = EvidencePlanningAndToolUseState.__new__(EvidencePlanningAndToolUseState)

    prompt_context = s5._build_prompt_context(state, {}, whitelist)

    assert prompt_context["research_plan"]["task_class"] == "ticket_price_lookup"
    assert state.structured_result["agent_core_research_plan"]["claim_plans"][0]["claim_type"] == "ticket_price"
