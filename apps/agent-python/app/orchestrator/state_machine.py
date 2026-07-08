"""Evidence-first travel agent state machine (SemanticFrame + AnswerMode routing).

Main pipeline::

    S0 UserInput
      → S1 BuildConversationContext
      → S2 QueryUnderstanding → SemanticFrame
      → S3 AnswerModeRouting → AnswerModeDecision
      → (early: clarification | model prior | evidence-preferred+prior)
      → S4 Region/Policy Check
    → S5 EvidencePlanningAndToolUseState (controlled tool/MCP loop)
    → S6 Evidence accumulation (within S5 loop)
      → S7 EvidenceAggregationState (LLM curation loop)
      → S8 Compose
      → S9 Citation/Limitations
      → S10 Response
"""

from uuid import uuid4

from app.catalog.location_resolver import resolve_city_country_from_text
from app.agents.information_need_planner import InformationNeedPlanner
from app.agents.composer_agent import ItineraryAgent
from app.agents.intent_agent import IntentAgent, RegionGateAgent
from app.agents.place_research_agent import PlaceResearchAgent
from app.agents.review_mining_agent import VerifierAgent
from app.agents.travel_task_to_user_goal_adapter import SUPPORTED_REGIONS, TravelTaskToUserGoalAdapter
from app.catalog.place_catalog import get_place_catalog
from app.config import get_settings
from app.orchestrator.states.evidence_accumulation_state import EvidenceAccumulationState
from app.llm_client import LLMClient
from app.orchestrator.answer_mode_router import AnswerModeRouter
from app.orchestrator.agent_core_store import ensure_agent_core_store, project_agent_core
from app.orchestrator.agent_core_supervisor import RootAgentSupervisor
from app.orchestrator.intent_profile_deriver import IntentProfileDeriver
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.citation_check import CitationChecker
from app.orchestrator.states.answer_composition_state import AnswerCompositionState
from app.orchestrator.states.evidence_aggregation_state import EvidenceAggregationState
from app.orchestrator.states.evidence_planning_and_tool_use_state import EvidencePlanningAndToolUseState
from app.orchestrator.states.llm_understanding_state import LLMUnderstandingState
from app.tools.capability_registry import CapabilityRegistry
from app.orchestrator.trace import TraceRecorder
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.evidence import Evidence
from app.schemas.evidence_gap_request import EvidenceGapLoopState, EvidenceGapRequest
from app.schemas.place_context import PlaceContext
from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.response import StructuredResult, TravelQueryResponse
from app.schemas.review import ReviewAspectResult
from app.schemas.travel_task import TravelTaskType
from app.schemas.intent_profile import EvidenceSensitivity, PrimaryIntent
from app.schemas.semantic_frame import AnswerMode, DecisionType, TaskFamily
from app.schemas.user_query import ConflictRecord, IntentType, RegionGateResult, TravelAgentState, UserContext, UserGoal
from app.tools import ToolRegistry
from app.tools.tool_router import ToolRouter


def _safe_s5_task_class(state: TravelAgentState) -> str | None:
    try:
        from app.orchestrator.agent_tool_catalog import resolve_s5_task_class

        return resolve_s5_task_class(state)
    except Exception:
        return None


class TravelAgentStateMachine:
    def __init__(self) -> None:
        self.llm = LLMClient()
        self.tools = ToolRegistry(llm_client=self.llm)
        self.place_research = PlaceResearchAgent(self.tools)
        self.verifier = VerifierAgent()
        self.catalog = get_place_catalog()
        self.capability_registry = CapabilityRegistry()
        self.tool_router = ToolRouter(self.capability_registry)
        self.answer_mode_router = AnswerModeRouter()
        self.contract_compiler = ResponseContractCompiler()
        self.llm_understanding_state = LLMUnderstandingState(self.llm)
        self.answer_composition_state = AnswerCompositionState(self.llm)
        self.evidence_aggregation_state = EvidenceAggregationState(self.llm)
        self.evidence_planning_state = EvidencePlanningAndToolUseState(
            self.llm,
            self.tools,
            self.tool_router,
        )
        self.evidence_accumulation_state = EvidenceAccumulationState(self.tools)

    async def _run_evidence_planning(self, state: TravelAgentState, **kwargs) -> TravelAgentState:
        return await self.evidence_planning_state.run(state, **kwargs)

    async def _run_evidence_accumulation(self, state: TravelAgentState, *, append: bool = False) -> TravelAgentState:
        return self.evidence_accumulation_state.run(state, append=append)

    async def _run_evidence_evaluation(self, state: TravelAgentState, target_label: str) -> TravelAgentState:
        return await self.evidence_aggregation_state.run(state, target_label=target_label)

    async def _run_evidence_curation(self, state: TravelAgentState, target_label: str) -> TravelAgentState:
        return await self._run_evidence_evaluation(state, target_label)

    @staticmethod
    def _init_gap_loop_state(state: TravelAgentState) -> None:
        if state.gap_loop_state is None:
            state.gap_loop_state = EvidenceGapLoopState(
                max_gap_rounds=get_settings().evidence_max_gap_rounds,
            )

    @staticmethod
    def _select_highest_priority_gap(state: TravelAgentState) -> EvidenceGapRequest | None:
        report = state.evidence_decision_report
        if not report or not report.evidence_gap_requests:
            return None
        priority_order = {"high": 0, "medium": 1, "low": 2}
        candidates = []
        loop = state.gap_loop_state
        for gap in report.evidence_gap_requests:
            gap.ensure_signature()
            if loop and gap.gap_signature in loop.gap_signatures:
                continue
            if loop and gap.gap_id in loop.failed_gap_ids:
                continue
            candidates.append(gap)
        if not candidates:
            return None
        return sorted(candidates, key=lambda g: priority_order.get(g.priority, 9))[0]

    def _should_run_gap_fill(self, state: TravelAgentState) -> bool:
        loop = state.gap_loop_state
        if not loop or loop.gap_round >= loop.max_gap_rounds:
            return False
        gap = self._select_highest_priority_gap(state)
        return gap is not None

    async def _run_evidence_loop(
        self,
        state: TravelAgentState,
        *,
        place_name: str,
        place_context: PlaceContext,
        reset_evidence: bool = True,
    ) -> TravelAgentState:
        self._init_gap_loop_state(state)
        state = await self._run_evidence_planning(
            state,
            place_name=place_name,
            place_context=place_context,
            reset_evidence=reset_evidence,
        )
        state = await self._run_evidence_accumulation(state)
        state = await self._run_evidence_evaluation(state, target_label=place_name)

        while self._should_run_gap_fill(state):
            gap = self._select_highest_priority_gap(state)
            if gap is None:
                break
            assert state.gap_loop_state is not None
            before = len(state.evidence)
            state.gap_loop_state.evidence_count_before_gap = before
            state.gap_loop_state.gap_round += 1
            gap.ensure_signature()
            state.gap_loop_state.gap_signatures.append(gap.gap_signature)
            state = await self.evidence_planning_state.run_gap_filling(state, gap)
            state = await self._run_evidence_accumulation(state, append=True)
            state = await self._run_evidence_evaluation(state, target_label=place_name)

        self._agent_core_record_evidence_pipeline(state)
        return state

    @staticmethod
    def _resolve_target_label(state: TravelAgentState) -> str:
        frame = state.semantic_frame
        goal = state.user_goal
        if frame and frame.entities.places:
            return frame.entities.places[0]
        if goal and goal.place_candidates:
            return goal.place_candidates[0]
        if frame and frame.entities.city:
            return frame.entities.city
        if goal and goal.destination_city:
            return goal.destination_city
        if frame and frame.entities.country:
            return frame.entities.country
        return "目的地"

    @property
    def query_understanding_state(self):
        """Backward-compatible alias."""
        return self.llm_understanding_state

    @staticmethod
    def _resolve_compose_mode(state: TravelAgentState) -> str:
        from app.orchestrator.nearby_task_orchestration import resolve_nearby_compose_mode
        from app.orchestrator.fact_lookup_task_orchestration import resolve_fact_lookup_compose_mode
        from app.orchestrator.place_disambiguation_composition import (
            should_present_place_disambiguation_at_s8,
        )

        nearby_mode = resolve_nearby_compose_mode(state)
        if nearby_mode:
            return nearby_mode
        fact_mode = resolve_fact_lookup_compose_mode(state)
        if fact_mode:
            return fact_mode
        if should_present_place_disambiguation_at_s8(state):
            return "place_disambiguation"
        task = state.travel_task
        if task and task.task_type == TravelTaskType.COMPARE_PLACES:
            return "compare"
        if task and task.task_type == TravelTaskType.ITINERARY_PLANNING:
            return "itinerary"
        if task and task.task_type == TravelTaskType.CROWD_INQUIRY:
            return "crowd"
        if task and task.task_type == TravelTaskType.SINGLE_PLACE_SUITABILITY:
            return "suitability"
        if state.intent_strategy:
            return state.intent_strategy.compose_mode
        frame = state.semantic_frame
        if frame:
            if frame.task_family == TaskFamily.FACT_LOOKUP:
                return "fact_lookup"
            if frame.decision_type == DecisionType.FACT_LOOKUP:
                return "fact_lookup"
            if frame.task_family == TaskFamily.SUITABILITY:
                return "suitability"
            if frame.decision_type == DecisionType.WHETHER_TO_GO:
                return "suitability"
        return "advisory"

    async def _run_answer_composition(self, state: TravelAgentState, **compose_kwargs) -> TravelAgentState:
        state = await self.answer_composition_state.run(state, **compose_kwargs)
        self._agent_core_record_answer_draft(state, compose_kwargs)
        return state

    async def run(self, query: str, user_context: dict | None = None, session_id: str | None = None) -> TravelQueryResponse:
        return await RootAgentSupervisor(self).run(
            query=query,
            user_context=user_context,
            session_id=session_id,
        )

    async def _dispatch_by_answer_mode(self, state: TravelAgentState) -> TravelQueryResponse:
        decision = state.answer_mode_decision
        mode = decision.answer_mode if decision else AnswerMode.EVIDENCE_REQUIRED

        if mode == AnswerMode.ESTIMATION_ALLOWED:
            if state.travel_task and state.travel_task.task_type == TravelTaskType.CROWD_INQUIRY:
                return await self._run_crowd_inquiry(state)
            return await self._run_evidence_pipeline(state)

        if mode == AnswerMode.EVIDENCE_PREFERRED and decision and decision.allow_knowledge_prior:
            resp = await self._run_evidence_pipeline(state)
            if self._evidence_preferred_response_sufficient(state, resp):
                return resp
            TraceRecorder.add(state, "✓ 工具证据不足以回答问题，回退 KnowledgePriorTool")
            return await self._run_advisory(state)

        if not state.travel_task:
            state.limitations.append("TravelTask 缺失，后续路由可能受限。")
            return self._to_response(state, 0.25)

        return await self._run_evidence_pipeline(state)

    async def _run_evidence_pipeline(
        self,
        state: TravelAgentState,
    ) -> TravelQueryResponse:
        state.query_plan = PlaceResearchAgent.build_query_plan(state.user_goal)
        if state.tool_execution_plan and state.tool_execution_plan.unsupported_needs:
            state.limitations.append(
                "以下信息需求暂无直接工具支撑：" + ", ".join(state.tool_execution_plan.unsupported_needs)
            )

        task_type = state.travel_task.task_type if state.travel_task else TravelTaskType.OPEN_ENDED_ADVICE
        if task_type == TravelTaskType.COMPARE_PLACES:
            return await self._run_compare(state)
        if task_type == TravelTaskType.ITINERARY_PLANNING:
            return await self._run_itinerary(state)
        if task_type == TravelTaskType.CROWD_INQUIRY:
            return await self._run_crowd_inquiry(state)
        return await self._run_single(state)

    async def _run_advisory(self, state: TravelAgentState) -> TravelQueryResponse:
        if state.travel_task and not state.information_needs:
            state.information_needs = InformationNeedPlanner.plan(state.travel_task)

        if not state.user_goal:
            frame = state.semantic_frame
            task = state.travel_task
            country = (frame.entities.country if frame else None) or (task.country if task else None)
            city = (frame.entities.city if frame else None) or (task.city if task else None)
            if country or city:
                state.user_goal = UserGoal(destination_country=country, destination_city=city)
                TraceRecorder.add(
                    state,
                    "✓ MODEL_PRIOR_ALLOWED → 进入 S5 工具规划（非直接 KnowledgePrior）",
                )

        frame = state.semantic_frame
        goal = state.user_goal

        target = self._resolve_target_label(state)
        state = await self._run_evidence_loop(
            state,
            place_name=target,
            place_context=self._place_context_for(state, target, 0),
            reset_evidence=True,
        )

        state = await self._run_answer_composition(
            state,
            compose_mode=self._resolve_compose_mode(state),
            target_label=target,
        )
        brief = state.evidence_brief
        base_conf = brief.overall_confidence if brief else 0.45
        confidence = self._citation_check(state, [], [], base_conf)
        return self._to_response(state, confidence)

    def _apply_region_gate(
        self,
        state: TravelAgentState,
        raw_query: str,
        gate_query: str,
        memory: ConversationMemory,
    ) -> TravelQueryResponse | None:
        state.region_gate = self._resolve_region_gate(state, raw_query, gate_query, memory)
        TraceRecorder.add(state, f"✓ 识别目的地区域：{state.region_gate.country or '未知'}")
        self._agent_core_record_input_contract(state)
        if not state.region_gate.supported:
            return self._unsupported(state)
        return None

    def _build_conversation_context(
        self,
        query: str,
        user_context: dict | None,
        session_id: str | None,
    ) -> tuple[UserContext, ConversationMemory, TravelAgentState]:
        ctx = UserContext.model_validate(user_context or {})
        memory = ConversationMemory.from_user_context(user_context)
        state = TravelAgentState(
            session_id=session_id or str(uuid4()),
            query_id=str(uuid4()),
            raw_user_query=query,
            conversation_memory=memory,
        )
        self._agent_core_init_run(state, user_context)
        return ctx, memory, state

    @staticmethod
    def _agent_core_init_run(state: TravelAgentState, user_context: dict | None) -> None:
        try:
            store = ensure_agent_core_store(state)
            store.set_phase("ingress", "running")
            store.add_phase_output(
                "ingress",
                kind="user_input",
                status="succeeded",
                payload={
                    "query": state.raw_user_query,
                    "session_id": state.session_id,
                    "query_id": state.query_id,
                    "user_context": user_context or {},
                },
            )
        except Exception:
            return

    @staticmethod
    def _agent_core_record_input_contract(state: TravelAgentState) -> None:
        try:
            store = ensure_agent_core_store(state)
            store.add_phase_output(
                "input_contract",
                kind="input_contract",
                status="succeeded" if state.response_contract else "draft",
                payload={
                    "semantic_frame": state.semantic_frame.model_dump(mode="json") if state.semantic_frame else None,
                    "travel_task": state.travel_task.model_dump(mode="json") if state.travel_task else None,
                    "answer_mode": (
                        state.answer_mode_decision.answer_mode.value
                        if state.answer_mode_decision and state.answer_mode_decision.answer_mode
                        else None
                    ),
                    "response_contract": state.response_contract.model_dump(mode="json") if state.response_contract else None,
                    "region_gate": state.region_gate.model_dump(mode="json") if state.region_gate else None,
                },
            )
        except Exception:
            return

    @staticmethod
    def _agent_core_record_evidence_pipeline(state: TravelAgentState) -> None:
        try:
            store = ensure_agent_core_store(state)
            sr = state.structured_result or {}
            usage_by_id, strength_by_id = TravelAgentStateMachine._agent_core_evidence_roles(state)
            for ev in state.evidence or []:
                if isinstance(ev, Evidence):
                    store.upsert_evidence(
                        ev,
                        usage_role=usage_by_id.get(ev.evidence_id, "context"),
                        strength=strength_by_id.get(ev.evidence_id, "unknown"),
                    )
            claim_decisions = []
            gaps = []
            if state.evidence_decision_report:
                claim_decisions = [
                    c.model_dump(mode="json") for c in state.evidence_decision_report.claim_decisions
                ]
                gaps = [
                    g.model_dump(mode="json") for g in state.evidence_decision_report.evidence_gap_requests
                ]
            has_research_plan = store.has_phase_output("research_plan", kind="research_plan")
            if not has_research_plan:
                store.add_phase_output(
                    "research_plan",
                    kind="research_plan_projection",
                    status="succeeded",
                    payload={
                        "information_needs": [
                            n.model_dump(mode="json") if hasattr(n, "model_dump") else str(n)
                            for n in (state.information_needs or [])
                        ],
                        "s5_task_class": _safe_s5_task_class(state),
                        "lookup_research_chain": sr.get("lookup_research_chain"),
                        "completed_search_task_ids": sr.get("completed_search_task_ids") or [],
                    },
                )
            store.add_phase_output(
                "evidence_acquisition",
                kind="evidence_batch",
                status="succeeded",
                evidence_refs=[ev.evidence_id for ev in state.evidence or [] if isinstance(ev, Evidence)],
                payload={
                    "evidence_count": len([ev for ev in state.evidence or [] if isinstance(ev, Evidence)]),
                    "tool_trace_count": len(state.tool_traces or []),
                    "completed_search_task_ids": sr.get("completed_search_task_ids") or [],
                    "attempted_search_task_ids": sr.get("attempted_search_task_ids") or [],
                    "source_names": sorted(
                        {
                            ev.source_name
                            for ev in state.evidence or []
                            if isinstance(ev, Evidence) and ev.source_name
                        }
                    ),
                },
            )
            store.add_phase_output(
                "evidence_review",
                kind="evidence_review",
                status="succeeded",
                payload={
                    "overall_confidence": (
                        state.evidence_brief.overall_confidence if state.evidence_brief else None
                    ),
                    "claim_decisions": claim_decisions,
                    "gaps": gaps,
                },
            )
        except Exception:
            return

    @staticmethod
    def _agent_core_evidence_roles(state: TravelAgentState) -> tuple[dict[str, str], dict[str, str]]:
        usage_by_id: dict[str, str] = {}
        strength_by_id: dict[str, str] = {}
        report = state.evidence_decision_report
        if not report:
            return usage_by_id, strength_by_id
        for decision in report.claim_decisions or []:
            if decision.adoption in {"adopt", "adopt_with_limitation"}:
                role = "answerable"
            elif decision.adoption == "candidate_only":
                role = "candidate"
            else:
                role = "context"
            strength = decision.adoption_level or decision.coverage_quality or "unknown"
            for evidence_id in decision.adopted_evidence_ids or []:
                usage_by_id[evidence_id] = role
                strength_by_id[evidence_id] = strength
            for evidence_id in decision.rejected_evidence_ids or []:
                usage_by_id[evidence_id] = "rejected"
                strength_by_id[evidence_id] = "rejected"
        for rejected in report.rejected_evidence or []:
            usage_by_id[rejected.evidence_id] = "rejected"
            strength_by_id[rejected.evidence_id] = "rejected"
        return usage_by_id, strength_by_id

    @staticmethod
    def _agent_core_record_answer_draft(state: TravelAgentState, compose_kwargs: dict) -> None:
        try:
            store = ensure_agent_core_store(state)
            payload = {
                "compose_mode": compose_kwargs.get("compose_mode"),
                "target_label": compose_kwargs.get("target_label"),
                "answer_preview": (state.final_response or "")[:500],
                "has_answer": bool((state.final_response or "").strip()),
            }
            artifact = store.add_artifact(artifact_type="answer", status="draft", payload=payload)
            store.add_phase_output(
                "answer_draft",
                kind="answer_artifact",
                status="pending_review",
                payload={"artifact_id": artifact.id, **payload},
            )
        except Exception:
            return

    @staticmethod
    def _agent_core_record_citation_guard(state: TravelAgentState, confidence: float) -> None:
        try:
            from app.orchestrator.agent_core_control_tools import AgentCoreControlTools

            store = ensure_agent_core_store(state)
            output = store.add_phase_output(
                "citation_guard",
                kind="citation_check",
                status="pending_review",
                payload={
                    "confidence": confidence,
                    "citation_check_result": (
                        state.citation_check_result.model_dump(mode="json")
                        if state.citation_check_result
                        else None
                    ),
                    "limitation_count": len(state.limitations or []),
                },
            )
            AgentCoreControlTools().approve_phase(
                state,
                phase="citation_guard",
                output_id=output.id,
                approved_by="root_agent:auto",
            )
        except Exception:
            return

    @staticmethod
    def _agent_core_record_delivery(state: TravelAgentState, confidence: float) -> None:
        try:
            from app.orchestrator.agent_core_control_tools import AgentCoreControlTools

            store = ensure_agent_core_store(state)
            answer_output = store.latest_phase_output("answer_draft", status="pending_review")
            if answer_output:
                AgentCoreControlTools().approve_phase(
                    state,
                    phase="answer_draft",
                    output_id=answer_output.id,
                    approved_by="root_agent:auto",
                )
            artifact = store.add_artifact(
                artifact_type="final_answer",
                status="succeeded",
                payload={
                    "answer_preview": (state.final_response or "")[:500],
                    "confidence": confidence,
                },
            )
            store.add_phase_output(
                "delivery",
                kind="final_answer",
                status="succeeded",
                payload={"artifact_id": artifact.id, "confidence": confidence},
            )
        except Exception:
            return

    def _derive_intent_profile(self, state: TravelAgentState) -> TravelAgentState:
        settings = get_settings()
        if not settings.intent_profile_enabled:
            return state
        frame = state.semantic_frame
        if not frame:
            return state
        profile = IntentProfileDeriver().derive(frame)
        state.intent_profile = profile
        state.intent_strategy = resolve_intent_strategy(profile)
        if profile and profile.primary_intent == PrimaryIntent.CLARIFICATION and state.intent_strategy:
            frame_amb = frame.place_ambiguity
            if frame_amb and frame_amb.candidates:
                state.intent_strategy = state.intent_strategy.model_copy(update={"skip_s5": False})
        if profile:
            subtypes = ",".join(profile.intent_subtypes[:4]) or "-"
            TraceRecorder.add(
                state,
                f"✓ IntentProfile: {profile.primary_intent.value} / "
                f"{profile.evidence_sensitivity.value} / subtypes=[{subtypes}]",
            )
        return state

    def _run_answer_mode_routing(self, state: TravelAgentState) -> TravelAgentState:
        frame = state.semantic_frame
        if not frame:
            state.limitations.append("SemanticFrame 缺失，回退到 TravelTask 路由。")
            return state

        available_caps = self.tool_router.available_capabilities()
        decision = self.answer_mode_router.route(frame, available_caps)
        state.answer_mode_decision = decision

        contract = self.contract_compiler.compile(
            frame,
            state.normalized_request,
            conversation_context=state.conversation_context.model_dump() if state.conversation_context else None,
            available_tools=set(available_caps),
            intent_profile=state.intent_profile,
        )
        contract.derived_debug_answer_mode = decision.answer_mode.value
        state.response_contract = contract

        claim_types = ", ".join(c.claim_type for c in contract.claim_requirements) or "none"
        TraceRecorder.add(state, f"✓ 已生成 ResponseContract：{claim_types}")
        required_summary = ", ".join(
            f"{c.claim_type}({c.priority})" for c in contract.claim_requirements if c.priority == "required"
        )
        if required_summary:
            TraceRecorder.add(state, f"✓ Claim 证据要求：{required_summary}")

        TraceRecorder.add(
            state,
            f"✓ 已判定回答模式（debug）：{decision.answer_mode.value}（{decision.reason}）",
        )
        state.limitations.extend(decision.limitations_to_add)
        state.limitations.extend(contract.limitations_to_add)
        from app.orchestrator.user_need_residual import attach_user_need_residual

        attach_user_need_residual(state)
        TraceRecorder.add(state, "✓ 已生成 UserNeedResidual（S5/S7/S8 需求残差）")
        self._agent_core_record_input_contract(state)
        return state

    @staticmethod
    def _requires_full_evidence_pipeline(contract) -> bool:
        return any(
            c.priority == "required" and not c.model_prior_allowed
            for c in contract.claim_requirements
        )

    @staticmethod
    def _allows_prior_advisory(contract) -> bool:
        required = [c for c in contract.claim_requirements if c.priority == "required"]
        if not required:
            return True
        return all(c.model_prior_allowed for c in required)

    @staticmethod
    def _has_required_hard_claims(contract) -> bool:
        return any(
            c.priority == "required" and not c.model_prior_allowed
            for c in contract.claim_requirements
        )

    def _dispatch_from_contract(self, state: TravelAgentState) -> str:
        contract = state.response_contract
        if not contract:
            return "legacy"
        if contract.clarification_policy.should_ask:
            frame = state.semantic_frame
            if (
                state.intent_profile
                and state.intent_profile.primary_intent == PrimaryIntent.CLARIFICATION
                and frame
                and frame.place_ambiguity
                and frame.place_ambiguity.candidates
                and state.intent_strategy
                and not state.intent_strategy.skip_s5
            ):
                return "evidence_pipeline"
            return "clarification"
        if state.intent_profile and state.intent_profile.primary_intent == PrimaryIntent.CLARIFICATION:
            frame = state.semantic_frame
            if (
                frame
                and frame.place_ambiguity
                and frame.place_ambiguity.candidates
                and state.intent_strategy
                and not state.intent_strategy.skip_s5
            ):
                return "evidence_pipeline"
            return "clarification"
        if self._has_required_hard_claims(contract):
            return "evidence_pipeline"
        if self._requires_full_evidence_pipeline(contract):
            return "evidence_pipeline"
        if get_settings().intent_profile_enabled and state.intent_profile:
            profile = state.intent_profile
            if profile.primary_intent in {
                PrimaryIntent.ADVISORY,
                PrimaryIntent.REVIEW_CHECK,
            } and profile.evidence_sensitivity != EvidenceSensitivity.LIVE_REQUIRED:
                if self._allows_prior_advisory(contract):
                    return "prior_advisory"
            return "evidence_pipeline"
        if self._allows_prior_advisory(contract):
            return "prior_advisory"
        return "evidence_pipeline"

    def _clarification_from_contract(self, state: TravelAgentState) -> TravelQueryResponse:
        contract = state.response_contract
        state.next_state = "clarification_response"
        prompt = (
            contract.clarification_policy.question
            if contract and contract.clarification_policy.question
            else "请补充具体地点或出行时间，以便继续分析。"
        )
        state.final_response = prompt
        confidence = state.query_understanding.confidence if state.query_understanding else 0.3
        return self._to_response(state, confidence)

    def _clarification_from_answer_mode(self, state: TravelAgentState) -> TravelQueryResponse:
        state.next_state = "clarification_response"
        state.final_response = (
            state.rewritten_query_result.clarification_prompt
            if state.rewritten_query_result and state.rewritten_query_result.clarification_prompt
            else "请补充具体地点或出行时间，以便继续分析。"
        )
        confidence = state.query_understanding.confidence if state.query_understanding else 0.3
        return self._to_response(state, confidence)

    async def _run_evidence_preferred_or_prior(
        self,
        state: TravelAgentState,
        ctx: UserContext,
        raw_query: str,
        gate_query: str,
        memory: ConversationMemory,
    ) -> TravelQueryResponse:
        if not self._has_place_target_from_frame(state):
            blocked = self._apply_region_gate(state, raw_query, gate_query, memory)
            if blocked:
                return blocked
            return await self._run_advisory(state)

        blocked = self._apply_region_gate(state, raw_query, gate_query, memory)
        if blocked:
            return blocked

        state.user_goal = await self._resolve_user_goal(state, ctx, gate_query)
        self._complete_context(state, ctx)

        resp = await self._run_evidence_pipeline(state)
        if state.evidence:
            return resp
        TraceRecorder.add(state, "✓ 工具证据不足，回退 KnowledgePriorTool")
        return await self._run_advisory(state)

    @staticmethod
    def _evidence_preferred_response_sufficient(state: TravelAgentState, resp) -> bool:
        """Do not discard a completed fact-lookup or nearby pipeline for advisory re-run."""
        frame = state.semantic_frame
        fact_needs = frozenset(
            {"elevation", "ticket_price", "opening_hours", "area", "general_fact", "address"}
        )
        nearby_needs = frozenset(
            {
                "nearby_food",
                "nearby_dining",
                "nearby_poi",
                "nearby_hotel",
                "nearby_rest_area",
                "nearby_parking",
                "nearby_toilet",
                "nearby_station",
            }
        )
        needs = set(frame.information_needs or []) if frame else set()
        is_fact_lookup = bool(
            frame
            and (
                frame.task_family.value == "fact_lookup"
                or frame.requires_exact_fact
                or bool(frame.information_needs and frame.information_needs[0] in fact_needs)
            )
        )
        is_nearby = bool(
            state.intent_profile
            and state.intent_profile.primary_intent == PrimaryIntent.NEARBY
        ) or bool(needs & nearby_needs)
        has_answer = bool((state.final_response or resp.answer or "").strip())
        has_evidence = bool(state.evidence) or len(resp.evidence_summary or []) > 0
        brief = state.evidence_brief
        has_curated = bool(brief and brief.curated_claims)

        if is_fact_lookup and has_answer and (has_evidence or has_curated):
            return True

        if is_nearby and has_answer and (has_evidence or has_curated):
            return True

        structured = resp.structured_result
        return (
            len(resp.evidence_summary or []) > 0
            and resp.confidence >= 0.30
            and structured is not None
            and (
                structured.recommendation is not None
                or bool(structured.places)
                or bool(structured.comparison)
            )
        )

    def _has_place_target_from_frame(self, state: TravelAgentState) -> bool:
        if state.semantic_frame and state.semantic_frame.entities.places:
            return True
        if state.travel_task and state.travel_task.places:
            return True
        return False

    async def _run_query_understanding(
        self,
        state: TravelAgentState,
        ctx: UserContext,
        user_context: dict | None,
    ) -> TravelAgentState:
        return await self.llm_understanding_state.run(state, ctx, user_context)

    async def _resolve_user_goal(self, state: TravelAgentState, ctx: UserContext, gate_query: str) -> UserGoal:
        qu_confidence = state.query_understanding.confidence if state.query_understanding else 0.0
        if TravelTaskToUserGoalAdapter.should_use_task(
            state.travel_task,
            state.query_understanding,
            qu_confidence,
        ):
            goal = TravelTaskToUserGoalAdapter.to_user_goal(state.travel_task, ctx)
            TraceRecorder.add(state, f"✓ 已从 TravelTask 生成 UserGoal：{goal.intent_type.value}")
            return goal

        goal = await IntentAgent.run(gate_query, self.llm, ctx)
        TraceRecorder.add(state, f"✓ IntentAgent fallback：{goal.intent_type.value}")
        return goal

    def _plan_tool_execution(self, state: TravelAgentState) -> list[str]:
        """Fallback candidate provider — main path uses EvidencePlanningAndToolUseState."""
        state.information_needs = InformationNeedPlanner.plan(state.travel_task)
        need_summary = ", ".join(f"{n.need_type.value}({n.priority.value})" for n in state.information_needs[:6])
        TraceRecorder.add(state, f"✓ 已生成信息需求：{need_summary}")

        state.tool_execution_plan = self.tool_router.route(state.information_needs, state.travel_task)
        tool_names = state.tool_execution_plan.selected_tools
        TraceRecorder.add(
            state,
            f"✓ 已根据能力选择工具：{', '.join(tool_names)}"
            + ("（含 fallback）" if state.tool_execution_plan.fallback_used else ""),
        )
        if state.tool_execution_plan.routing_explanation:
            TraceRecorder.add(state, f"✓ 路由说明：{state.tool_execution_plan.routing_explanation[0]}")
        return tool_names

    def _resolve_region_gate(
        self,
        state: TravelAgentState,
        raw_query: str,
        gate_query: str,
        memory: ConversationMemory,
    ) -> RegionGateResult:
        task = state.travel_task
        if task and task.country in SUPPORTED_REGIONS:
            return RegionGateResult(
                supported=True,
                country=task.country,
                city=task.city,
                reason="Resolved from TravelTask",
            )

        region = RegionGateAgent.run(raw_query)
        if not region.supported:
            region = RegionGateAgent.run(gate_query)

        if not region.supported:
            frame = None
            if state.normalized_request:
                country = next((e.country for e in state.normalized_request.entities if e.country), None)
                city = next((e.city for e in state.normalized_request.entities if e.city), None)
                if country in SUPPORTED_REGIONS:
                    return RegionGateResult(
                        supported=True,
                        country=country,
                        city=city,
                        reason="Resolved from NormalizedUserRequest",
                    )
            if state.query_understanding and state.query_understanding.semantic_frame:
                frame = state.query_understanding.semantic_frame
            elif state.semantic_frame:
                frame = state.semantic_frame
            if frame and frame.entities.country in SUPPORTED_REGIONS:
                return RegionGateResult(
                    supported=True,
                    country=frame.entities.country,
                    city=frame.entities.city,
                    reason="Resolved from semantic frame",
                )

        settings = get_settings()
        if not region.supported and state.rewritten_query_result and settings.place_resolution_use_mock:
            for key in ("here", "这里", "place", "这个地方"):
                pname = state.rewritten_query_result.resolved_references.get(key)
                if pname:
                    loc = self.catalog.get_place_location(pname)
                    if loc:
                        return RegionGateResult(
                            supported=True,
                            country=loc.country,
                            city=loc.city,
                            reason=f"Resolved from place catalog: {pname}",
                        )

        if not region.supported and settings.place_resolution_use_mock:
            for place in self.catalog.find_places_in_text(gate_query) or self.catalog.find_places_in_text(raw_query):
                loc = self.catalog.get_place_location(place)
                if loc:
                    return RegionGateResult(
                        supported=True,
                        country=loc.country,
                        city=loc.city,
                        reason=f"Resolved from place catalog: {place}",
                    )

        if not region.supported:
            for text in (raw_query, gate_query):
                hit = resolve_city_country_from_text(text)
                if hit:
                    country, city = hit
                    return RegionGateResult(
                        supported=True,
                        country=country,
                        city=city,
                        reason=f"Resolved from city catalog: {city}",
                    )

        if not region.supported and memory.last_country:
            return RegionGateResult(
                supported=True,
                country=memory.last_country,
                city=memory.last_city,
                reason="Resolved from conversation memory",
            )
        return region

    def _build_place_contexts(self, goal: UserGoal) -> list[PlaceContext]:
        return [self.catalog.resolve_place_context(place) for place in goal.place_candidates]

    def _backfill_location_from_places(self, state: TravelAgentState) -> None:
        goal = state.user_goal
        if not goal:
            return
        if state.travel_task and state.travel_task.places:
            state.place_contexts = state.travel_task.places
        else:
            state.place_contexts = self._build_place_contexts(goal)

        if goal.intent_type == IntentType.COMPARE_PLACES:
            cities = {c.city for c in state.place_contexts if c.city}
            countries = {c.country for c in state.place_contexts if c.country}
            if len(cities) == 1 and len(countries) == 1:
                goal.destination_city = next(iter(cities))
                goal.destination_country = next(iter(countries))
            return

        if state.place_contexts and state.place_contexts[0].country and state.place_contexts[0].city:
            goal.destination_country = state.place_contexts[0].country
            goal.destination_city = state.place_contexts[0].city

    def _complete_context(self, state: TravelAgentState, ctx: UserContext) -> None:
        goal = state.user_goal
        if not goal:
            return
        if ctx.travel_date and not goal.travel_date:
            goal.travel_date = ctx.travel_date
        if ctx.party:
            for p in ctx.party:
                if p not in goal.party:
                    goal.party.append(p)
        if ctx.start_location and not goal.start_location:
            goal.start_location = ctx.start_location
        if state.query_understanding:
            goal.constraints = list(dict.fromkeys(goal.constraints + state.query_understanding.assumptions))
        if not goal.place_candidates:
            maybe = self.catalog.normalize_place_name(state.raw_user_query)
            if maybe:
                goal.place_candidates = [maybe]
            elif state.rewritten_query_result:
                for key in ("here", "这里", "place"):
                    ref = state.rewritten_query_result.resolved_references.get(key)
                    if ref:
                        goal.place_candidates = [ref]
                        break
        self._backfill_location_from_places(state)
        if not goal.destination_city and state.region_gate and state.region_gate.city:
            goal.destination_city = state.region_gate.city
        if not goal.destination_country and state.region_gate and state.region_gate.country:
            goal.destination_country = state.region_gate.country

        assumptions: list[str] = []
        if state.query_understanding:
            assumptions.extend(state.query_understanding.assumptions)
        if not goal.travel_date:
            assumptions.append("未提供出行日期，天气评估使用默认近日假设。")
        if not goal.party:
            assumptions.append("未提供同行人画像，按一般游客评估。")
        state.limitations.extend(assumptions)

    def _collect_field_summary(self, state: TravelAgentState, fact_sheets: list[PlaceFactSheet]) -> None:
        rows: list[dict] = []
        for sheet in fact_sheets:
            rows.extend(sheet.to_field_evidence_summary())
        state.field_evidence_summary = rows

    def _sync_tool_traces(self, state: TravelAgentState) -> None:
        state.tool_traces = list(self.tools.traces)

    def _place_context_for(self, state: TravelAgentState, place: str, index: int) -> PlaceContext:
        if index < len(state.place_contexts):
            return state.place_contexts[index]
        return self.catalog.resolve_place_context(place)

    def _apply_crowd_limitations(self, state: TravelAgentState) -> None:
        state.limitations.append(
            "未接入实时人流/排队数据，拥挤判断基于评价摘要、地图热门程度代理与日期因素估算。"
        )
        if state.tool_execution_plan and state.tool_execution_plan.fallback_used:
            state.limitations.append("部分信息通过 fallback 工具补充，置信度受限。")

    async def _run_crowd_inquiry(self, state: TravelAgentState) -> TravelQueryResponse:
        goal = state.user_goal
        place = goal.place_candidates[0] if goal and goal.place_candidates else None
        if not place and state.travel_task and state.travel_task.places:
            place = state.travel_task.places[0].canonical_name
        if not place:
            state.limitations.append("未能识别具体景点。")
            state.final_response = "请提供具体景点名称，以便评估人流情况。"
            return self._to_response(state, 0.25)

        canonical = self.catalog.normalize_place_name(place) or place
        self._backfill_location_from_places(state)
        self._apply_crowd_limitations(state)

        place_ctx = self._place_context_for(state, place, 0)
        state = await self._run_evidence_loop(
            state,
            place_name=canonical,
            place_context=place_ctx,
            reset_evidence=True,
        )

        state = await self._run_answer_composition(
            state,
            compose_mode=self._resolve_compose_mode(state),
            target_label=canonical,
            place_name=canonical,
        )
        state.structured_result = StructuredResult(
            places=[{"name": canonical}],
        ).model_dump()

        brief = state.evidence_brief
        base_conf = min(brief.overall_confidence if brief else 0.5, 0.75)
        confidence = self._citation_check(state, [], [], base_conf)
        return self._to_response(state, confidence)

    async def _run_single(self, state: TravelAgentState) -> TravelQueryResponse:
        goal = state.user_goal
        place = goal.place_candidates[0] if goal and goal.place_candidates else None
        if not place:
            state.limitations.append("未能识别具体景点，返回区域级有限建议。")
            state.final_response = "请提供具体景点名称，以便生成证据驱动的情报卡。"
            return self._to_response(state, 0.2)

        canonical = self.catalog.normalize_place_name(place) or place
        self._backfill_location_from_places(state)
        if not self.catalog.has_place(canonical):
            state.limitations.append(f"{place} 暂无结构化 mock 数据，部分结论可能不完整。")

        place_ctx = self._place_context_for(state, place, 0)
        state = await self._run_evidence_loop(
            state,
            place_name=canonical,
            place_context=place_ctx,
            reset_evidence=True,
        )
        evidence = [ev for ev in state.evidence if isinstance(ev, Evidence)]
        TraceRecorder.add(state, "✓ 查询官方/地图/交通/评价/天气证据")

        issues = self.verifier.validate(evidence)
        state.limitations.extend(issues)
        conflicts = self.verifier.detect_conflicts(evidence)
        state.conflicts = [ConflictRecord(**c) for c in conflicts]
        if conflicts:
            TraceRecorder.add(state, "✓ 发现来源冲突，已优先采用官方信息")

        brief = state.evidence_brief
        if brief:
            state.scores.confidence = brief.overall_confidence

        state = await self._run_answer_composition(
            state,
            compose_mode=self._resolve_compose_mode(state),
            target_label=canonical,
            place_name=canonical,
        )
        state.structured_result = StructuredResult(
            places=[{"name": canonical}],
        ).model_dump()

        base_conf = brief.overall_confidence if brief else 0.5
        confidence = self._citation_check(state, [], [], base_conf)
        return self._to_response(state, confidence)

    async def _run_compare(self, state: TravelAgentState) -> TravelQueryResponse:
        from app.orchestrator.comparison_helpers import (
            comparison_places_from_state,
            reset_per_place_search_state,
        )

        places = comparison_places_from_state(state)
        goal = state.user_goal
        if len(places) < 2 and goal:
            places = list(goal.place_candidates or [])
        if len(places) < 2:
            state.limitations.append("比较任务需要至少两个景点。")

        self._backfill_location_from_places(state)
        canonical_places: list[str] = []
        state.comparison_mode = True
        state.comparison_peer_places = list(places[:4])

        for idx, place in enumerate(places[:4]):
            canonical = self.catalog.normalize_place_name(place) or place
            canonical_places.append(canonical)
            state.comparison_active_place = canonical
            reset_per_place_search_state(state)
            self._init_gap_loop_state(state)
            place_ctx = self._place_context_for(state, place, idx)
            state = await self._run_evidence_loop(
                state,
                place_name=canonical,
                place_context=place_ctx,
                reset_evidence=(idx == 0),
            )
            TraceRecorder.add(state, f"✓ 已完成 {canonical} 情报检索（comparison per-place）")

        state = await self._run_comparison_route_probe(state, canonical_places)

        state.conflicts = [
            ConflictRecord(**c) for c in self.verifier.detect_conflicts(state.evidence)
        ]

        compare_label = " vs ".join(canonical_places) if canonical_places else "比较"
        state = await self._run_evidence_evaluation(state, target_label=compare_label)

        state.structured_result = {
            **(state.structured_result or {}),
            **StructuredResult(
                places=[{"name": n} for n in canonical_places],
            ).model_dump(),
        }
        state = await self._run_answer_composition(
            state,
            compose_mode=self._resolve_compose_mode(state),
            target_label=compare_label,
            place_names=canonical_places,
        )

        brief = state.evidence_brief
        base_conf = brief.overall_confidence if brief else 0.5
        confidence = self._citation_check(state, [], [], base_conf)
        state.comparison_active_place = None
        return self._to_response(state, confidence)

    async def _run_comparison_route_probe(
        self,
        state: TravelAgentState,
        places: list[str],
    ) -> TravelAgentState:
        if len(places) < 2:
            return state
        from app.orchestrator.comparison_helpers import (
            disambiguated_place_label,
            stamp_evidence_place,
        )

        origin, dest = places[0], places[1]
        frame = state.semantic_frame
        city = frame.entities.city if frame and frame.entities else None
        region = frame.entities.region if frame and frame.entities else None
        country = frame.entities.country if frame and frame.entities else None
        prior_evidence: list = []
        for place in (origin, dest):
            try:
                search_ev = await self.tools.run_tool(
                    "baidu_place_search_mcp",
                    query=place,
                    place_name=place,
                    city=city,
                    region=region,
                    country=country,
                    information_need="route_plan",
                )
                if search_ev:
                    stamped = stamp_evidence_place(list(search_ev), place)
                    state.evidence.extend(stamped)
                    prior_evidence.extend(stamped)
                    TraceRecorder.add(state, f"✓ comparison place search: {place}")
            except Exception:
                continue

        resolved_origin = disambiguated_place_label(
            origin, city=city, region=region, country=country
        )
        resolved_dest = disambiguated_place_label(dest, city=city, region=region, country=country)
        for tool_name in ("baidu_route_matrix_mcp", "baidu_route_mcp"):
            try:
                evidence = await self.tools.run_tool(
                    tool_name,
                    place_name=origin,
                    origin=resolved_origin,
                    destination=resolved_dest,
                    city=city,
                    region=region,
                    country=country,
                    prior_evidence=prior_evidence,
                    information_need="route_plan",
                    query=f"{resolved_origin} 到 {resolved_dest} 交通",
                )
                if evidence:
                    state.evidence.extend(stamp_evidence_place(list(evidence), origin))
                    TraceRecorder.add(state, f"✓ comparison route probe: {tool_name}")
                    break
            except Exception:
                continue
        return state

    async def _run_itinerary(self, state: TravelAgentState) -> TravelQueryResponse:
        goal = state.user_goal
        self._backfill_location_from_places(state)
        plan = ItineraryAgent.build(goal)
        places = [i.place_name for i in plan.items if i.place_name]

        for idx, place in enumerate(places):
            canonical = self.catalog.normalize_place_name(place) or place
            place_ctx = self._place_context_for(state, place, idx)
            state = await self._run_evidence_loop(
                state,
                place_name=canonical,
                place_context=place_ctx,
                reset_evidence=(idx == 0),
            )
            TraceRecorder.add(state, f"✓ 检索 {canonical} 交通/开放信息")

        target = "、".join(places) if places else "行程"
        state = await self._run_evidence_evaluation(state, target_label=target)
        state.structured_result = StructuredResult(
            itinerary=plan.model_dump(),
            places=[{"name": p} for p in places],
        ).model_dump()
        state = await self._run_answer_composition(
            state,
            compose_mode=self._resolve_compose_mode(state),
            target_label=target,
            plan=plan,
        )
        brief = state.evidence_brief
        base_conf = brief.overall_confidence if brief else 0.74
        confidence = self._citation_check(state, [], [], base_conf)
        return self._to_response(state, confidence)

    def _unsupported(self, state: TravelAgentState) -> TravelQueryResponse:
        state.final_response = (
            "当前版本重点支持日本、中国、韩国。\n"
            "您的查询暂未落在重点支持范围内，可先告知具体国家/城市/景点，或等待后续版本扩展。"
        )
        state.limitations.append(state.region_gate.reason if state.region_gate else "Unsupported region")
        return self._to_response(state, 0.3)

    def _citation_check(
        self,
        state: TravelAgentState,
        fact_sheets: list[PlaceFactSheet],
        review_results: list[ReviewAspectResult],
        base_confidence: float,
    ) -> float:
        result = CitationChecker.check(
            state.final_response or "",
            fact_sheets,
            review_results,
            base_confidence,
        )
        state.citation_check_result = result
        state.limitations.extend(result.limitations)
        TraceRecorder.add(state, "✓ 完成引用与限制检查")
        self._agent_core_record_citation_guard(state, result.confidence)
        return result.confidence

    @staticmethod
    def _semantic_frame_summary(state: TravelAgentState) -> dict | None:
        sf = state.semantic_frame
        if not sf:
            return None
        return {
            "query_scope": sf.query_scope.value,
            "task_family": sf.task_family.value,
            "decision_type": sf.decision_type.value,
            "time_scope": sf.time_scope.value,
            "entities": sf.entities.model_dump(),
            "information_needs": sf.information_needs,
            "requires_exact_fact": sf.requires_exact_fact,
            "requires_live_data": sf.requires_live_data,
            "can_answer_with_model_prior": sf.can_answer_with_model_prior,
            "confidence": sf.confidence,
        }

    def _to_response(self, state: TravelAgentState, confidence: float) -> TravelQueryResponse:
        from app.orchestrator.response_sanitizer import sanitize_answer_text, sanitize_limitations

        self._sync_tool_traces(state)
        evidence_summary = [
            {
                "evidence_id": ev.evidence_id,
                "source_name": ev.source_name,
                "source_type": ev.source_type.value,
                "source_url": ev.source_url,
                "place_name": ev.place_name,
                "confidence": ev.confidence,
            }
            for ev in state.evidence
            if isinstance(ev, Evidence)
        ]
        structured = StructuredResult.model_validate(state.structured_result or {})
        sr = state.structured_result or {}
        orchestration_summary: dict = {}
        for key in (
            "subagent_results",
            "fact_lookup_pipeline_runs",
            "fact_anchor",
            "lookup_research_chain",
            "nearby_enrichment_runs",
            "completed_search_task_ids",
            "subagent_evidence_gate_rejects",
        ):
            value = sr.get(key)
            if value:
                orchestration_summary[key] = value
        try:
            from app.orchestrator.agent_tool_catalog import resolve_s5_task_class

            orchestration_summary["s5_task_class"] = resolve_s5_task_class(state)
        except Exception:
            pass
        self._agent_core_record_delivery(state, confidence)
        agent_core_projection = project_agent_core(state)
        if agent_core_projection:
            orchestration_summary["agent_core_projection"] = agent_core_projection
        answer_mode = (
            state.response_contract.derived_debug_answer_mode
            if state.response_contract and state.response_contract.derived_debug_answer_mode
            else (state.answer_mode_decision.answer_mode.value if state.answer_mode_decision else None)
        )
        return TravelQueryResponse(
            answer=sanitize_answer_text(state.final_response or ""),
            structured_result=structured,
            visible_trace=state.visible_trace,
            evidence_summary=evidence_summary,
            field_evidence_summary=state.field_evidence_summary,
            conflicts=[c.model_dump() for c in state.conflicts],
            limitations=sanitize_limitations(state.limitations),
            confidence=confidence,
            citation_check_result=state.citation_check_result.model_dump() if state.citation_check_result else None,
            tool_traces=[t.model_dump() for t in state.tool_traces],
            session_id=state.session_id,
            query_id=state.query_id,
            semantic_frame_summary=self._semantic_frame_summary(state),
            answer_mode=answer_mode,
            orchestration_summary=orchestration_summary or None,
        )
