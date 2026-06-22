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
      → S7 Evidence Aggregation
      → S8 Compose
      → S9 Citation/Limitations
      → S10 Response
"""

from uuid import uuid4

from app.agents.information_need_planner import InformationNeedPlanner
from app.agents.composer_agent import ComposerAgent, ItineraryAgent
from app.agents.intent_agent import IntentAgent, RegionGateAgent
from app.agents.place_research_agent import PlaceResearchAgent
from app.agents.review_mining_agent import ReviewAspectMiningAgent, VerifierAgent
from app.agents.suitability_scorer import TravelSuitabilityScorer
from app.agents.travel_task_to_user_goal_adapter import SUPPORTED_REGIONS, TravelTaskToUserGoalAdapter
from app.catalog.location_resolver import resolve_city_country_from_text
from app.catalog.place_catalog import get_place_catalog
from app.config import get_settings
from app.llm_client import LLMClient
from app.orchestrator.answer_mode_router import AnswerModeRouter
from app.orchestrator.citation_check import CitationChecker
from app.orchestrator.evidence_aggregator import EvidenceAggregator
from app.orchestrator.states.answer_composition_state import AnswerCompositionState
from app.orchestrator.states.evidence_planning_and_tool_use_state import EvidencePlanningAndToolUseState
from app.orchestrator.states.llm_understanding_state import LLMUnderstandingState
from app.tools.capability_registry import CapabilityRegistry
from app.orchestrator.trace import TraceRecorder
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.evidence import Evidence
from app.schemas.place_context import PlaceContext
from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.response import StructuredResult, TravelQueryResponse
from app.schemas.review import ReviewAspectResult
from app.schemas.travel_task import TravelTaskType
from app.schemas.semantic_frame import AnswerMode, DecisionType
from app.schemas.user_query import ConflictRecord, IntentType, RegionGateResult, TravelAgentState, UserContext, UserGoal
from app.tools import ToolRegistry
from app.tools.tool_router import ToolRouter


class TravelAgentStateMachine:
    def __init__(self) -> None:
        self.llm = LLMClient()
        self.tools = ToolRegistry(llm_client=self.llm)
        self.place_research = PlaceResearchAgent(self.tools)
        self.review_agent = ReviewAspectMiningAgent(self.tools)
        self.scorer = TravelSuitabilityScorer()
        self.verifier = VerifierAgent()
        self.aggregator = EvidenceAggregator()
        self.catalog = get_place_catalog()
        self.capability_registry = CapabilityRegistry()
        self.tool_router = ToolRouter(self.capability_registry)
        self.answer_mode_router = AnswerModeRouter()
        self.llm_understanding_state = LLMUnderstandingState(self.llm)
        self.answer_composition_state = AnswerCompositionState(self.llm)
        self.evidence_planning_state = EvidencePlanningAndToolUseState(
            self.llm,
            self.tools,
            self.tool_router,
        )

    async def _run_evidence_planning(self, state: TravelAgentState, **kwargs) -> TravelAgentState:
        return await self.evidence_planning_state.run(state, **kwargs)

    @property
    def query_understanding_state(self):
        """Backward-compatible alias."""
        return self.llm_understanding_state

    async def _run_answer_composition(self, state: TravelAgentState, **compose_kwargs) -> TravelAgentState:
        return await self.answer_composition_state.run(state, **compose_kwargs)

    async def run(self, query: str, user_context: dict | None = None, session_id: str | None = None) -> TravelQueryResponse:
        self.tools.clear_traces()
        ctx, memory, state = self._build_conversation_context(query, user_context, session_id)

        # S2: QueryUnderstanding → SemanticFrame
        state = await self._run_query_understanding(state, ctx, user_context)
        if state.next_state == "clarification_response":
            confidence = state.query_understanding.confidence if state.query_understanding else 0.3
            return self._to_response(state, confidence)

        # S3: AnswerModeRouting（早于 RegionGate / place 判断）
        state = self._run_answer_mode_routing(state)
        decision = state.answer_mode_decision
        mode = decision.answer_mode if decision else AnswerMode.EVIDENCE_REQUIRED

        if mode == AnswerMode.CLARIFICATION_REQUIRED:
            return self._clarification_from_answer_mode(state)
        if mode == AnswerMode.UNSUPPORTED:
            state.final_response = "暂无法理解该问题类型，请补充国家/城市/景点或换一种问法。"
            return self._to_response(state, 0.25)
        if mode == AnswerMode.MODEL_PRIOR_ALLOWED:
            gate_query = state.rewritten_query_result.rewritten_query if state.rewritten_query_result else query
            blocked = self._apply_region_gate(state, query, gate_query, memory)
            if blocked:
                return blocked
            return await self._run_advisory(state)
        if mode == AnswerMode.EVIDENCE_PREFERRED and decision and decision.allow_knowledge_prior:
            gate_query = state.rewritten_query_result.rewritten_query if state.rewritten_query_result else query
            return await self._run_evidence_preferred_or_prior(state, ctx, query, gate_query, memory)

        gate_query = state.rewritten_query_result.rewritten_query if state.rewritten_query_result else query

        # S4: RegionGate
        blocked = self._apply_region_gate(state, query, gate_query, memory)
        if blocked:
            return blocked

        # S5: UserGoal + context
        state.user_goal = await self._resolve_user_goal(state, ctx, gate_query)
        self._complete_context(state, ctx)
        TraceRecorder.add(state, f"✓ 识别用户画像：{', '.join(p.value for p in state.user_goal.party) or '一般游客'}")

        # S6–S10: 按 AnswerMode 进入工具链 / 聚合 / 合成
        return await self._dispatch_by_answer_mode(state)

    async def _dispatch_by_answer_mode(self, state: TravelAgentState) -> TravelQueryResponse:
        decision = state.answer_mode_decision
        mode = decision.answer_mode if decision else AnswerMode.EVIDENCE_REQUIRED

        if mode == AnswerMode.ESTIMATION_ALLOWED:
            if state.travel_task and state.travel_task.task_type == TravelTaskType.CROWD_INQUIRY:
                return await self._run_crowd_inquiry(state)
            return await self._run_evidence_pipeline(state)

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
        frame = state.semantic_frame
        goal = state.user_goal

        state = await self._run_evidence_planning(state, reset_evidence=True, advisory_mode=True)
        evidence = [ev for ev in state.evidence if isinstance(ev, Evidence)]
        self._sync_tool_traces(state)

        target = (
            (frame.entities.places[0] if frame and frame.entities.places else None)
            or (frame.entities.city if frame else None)
            or (goal.destination_city if goal else None)
            or (frame.entities.country if frame else None)
            or "目的地"
        )
        state.field_evidence_summary = []
        for ev in evidence:
            for claim in ev.claims:
                state.field_evidence_summary.append(
                    {
                        "field": claim.claim_type.value,
                        "value": claim.value,
                        "source_ids": [ev.evidence_id],
                        "confidence": claim.confidence,
                        "source_names": [ev.source_name],
                    }
                )

        state = await self._run_answer_composition(
            state,
            compose_mode="advisory",
            target_label=target,
        )
        base_conf = min((ev.confidence for ev in evidence), default=0.55) if evidence else 0.45
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
        return ctx, memory, state

    def _run_answer_mode_routing(self, state: TravelAgentState) -> TravelAgentState:
        frame = state.semantic_frame
        if not frame:
            state.limitations.append("SemanticFrame 缺失，回退到 TravelTask 路由。")
            return state

        available_caps = self.tool_router.available_capabilities()
        decision = self.answer_mode_router.route(frame, available_caps)
        state.answer_mode_decision = decision
        TraceRecorder.add(
            state,
            f"✓ 已判定回答模式：{decision.answer_mode.value}（{decision.reason}）",
        )
        state.limitations.extend(decision.limitations_to_add)
        return state

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
        state = await self._run_evidence_planning(
            state,
            place_name=canonical,
            place_context=place_ctx,
            reset_evidence=True,
        )
        evidence = [ev for ev in state.evidence if isinstance(ev, Evidence)]
        self._sync_tool_traces(state)

        fact_sheet = self.aggregator.aggregate(canonical, evidence, [])
        self._collect_field_summary(state, [fact_sheet])
        review_result = await self.review_agent.run(canonical, goal)
        recommendation = self.scorer.score_place(canonical, fact_sheet, review_result, goal, [])

        state = await self._run_answer_composition(
            state,
            compose_mode="crowd",
            place_name=canonical,
            fact_sheet=fact_sheet,
            review=review_result,
        )
        state.structured_result = StructuredResult(
            recommendation=recommendation,
            places=[{"name": canonical, "fact_sheet": fact_sheet.model_dump()}],
        ).model_dump()

        confidence = self._citation_check(state, [fact_sheet], [review_result], min(recommendation.confidence, 0.75))
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
        state = await self._run_evidence_planning(
            state,
            place_name=canonical,
            place_context=place_ctx,
            reset_evidence=True,
        )
        evidence = [ev for ev in state.evidence if isinstance(ev, Evidence)]
        self._sync_tool_traces(state)
        TraceRecorder.add(state, "✓ 查询官方/地图/交通/评价/天气证据")

        issues = self.verifier.validate(evidence)
        state.limitations.extend(issues)
        conflicts = self.verifier.detect_conflicts(evidence)
        state.conflicts = [ConflictRecord(**c) for c in conflicts]
        if conflicts:
            TraceRecorder.add(state, "✓ 发现来源冲突，已优先采用官方信息")

        fact_sheet = self.aggregator.aggregate(canonical, evidence, state.conflicts)
        self._collect_field_summary(state, [fact_sheet])
        review_result = await self.review_agent.run(canonical, goal)
        state.review_aspects.append(review_result.model_dump())
        TraceRecorder.add(state, "✓ 完成评价维度抽取")

        recommendation = self.scorer.score_place(canonical, fact_sheet, review_result, goal, state.conflicts)
        state.scores.overall_suitability = recommendation.overall_score
        state.scores.confidence = recommendation.confidence
        TraceRecorder.add(state, "✓ 完成画像适配评分")

        state = await self._run_answer_composition(
            state,
            compose_mode="single",
            place_name=canonical,
            recommendation=recommendation,
            review=review_result,
            fact_sheet=fact_sheet,
        )
        state.structured_result = StructuredResult(
            recommendation=recommendation,
            places=[{"name": canonical, "fact_sheet": fact_sheet.model_dump()}],
        ).model_dump()

        confidence = self._citation_check(state, [fact_sheet], [review_result], recommendation.confidence)
        return self._to_response(state, confidence)

    async def _run_compare(self, state: TravelAgentState) -> TravelQueryResponse:
        goal = state.user_goal
        places = goal.place_candidates if goal else []
        if len(places) < 2:
            state.limitations.append("比较任务需要至少两个景点。")

        self._backfill_location_from_places(state)
        ranked_data: list[tuple[str, object, ReviewAspectResult, PlaceFactSheet]] = []
        all_evidence: list[Evidence] = []

        for idx, place in enumerate(places[:4]):
            canonical = self.catalog.normalize_place_name(place) or place
            place_ctx = self._place_context_for(state, place, idx)
            before = len(state.evidence)
            state = await self._run_evidence_planning(
                state,
                place_name=canonical,
                place_context=place_ctx,
                reset_evidence=(idx == 0),
            )
            ev = [e for e in state.evidence[before:] if isinstance(e, Evidence)]
            all_evidence.extend(ev)
            conflicts = [ConflictRecord(**c) for c in self.verifier.detect_conflicts(ev)]
            fact_sheet = self.aggregator.aggregate(canonical, ev, conflicts)
            review = await self.review_agent.run(canonical, goal)
            rec = self.scorer.score_place(canonical, fact_sheet, review, goal, conflicts)
            ranked_data.append((canonical, rec, review, fact_sheet))
            TraceRecorder.add(state, f"✓ 已完成 {canonical} 情报检索与评分")

        ranked = sorted(ranked_data, key=lambda x: x[1].overall_score, reverse=True)
        rows = ComposerAgent.build_comparison_rows(ranked)
        state.evidence = all_evidence
        self._sync_tool_traces(state)
        state.conflicts = [ConflictRecord(**c) for c in self.verifier.detect_conflicts(all_evidence)]
        fact_sheets = [fs for _, _, _, fs in ranked]
        self._collect_field_summary(state, fact_sheets)
        state.structured_result = StructuredResult(
            comparison=[r.model_dump() for r in rows],
            places=[{"name": n, "fact_sheet": fs.model_dump()} for n, _, _, fs in ranked],
        ).model_dump()
        state = await self._run_answer_composition(state, compose_mode="compare", ranked=ranked)

        reviews = [r for _, _, r, _ in ranked]
        top_conf = ranked[0][1].confidence if ranked else 0.5
        confidence = self._citation_check(state, fact_sheets, reviews, top_conf)
        return self._to_response(state, confidence)

    async def _run_itinerary(self, state: TravelAgentState) -> TravelQueryResponse:
        goal = state.user_goal
        self._backfill_location_from_places(state)
        plan = ItineraryAgent.build(goal)
        places = [i.place_name for i in plan.items if i.place_name]
        all_evidence: list[Evidence] = []

        for idx, place in enumerate(places):
            canonical = self.catalog.normalize_place_name(place) or place
            place_ctx = self._place_context_for(state, place, idx)
            before = len(state.evidence)
            state = await self._run_evidence_planning(
                state,
                place_name=canonical,
                place_context=place_ctx,
                reset_evidence=False if idx else True,
            )
            all_evidence.extend(
                [e for e in state.evidence[before:] if isinstance(e, Evidence)]
            )
            TraceRecorder.add(state, f"✓ 检索 {canonical} 交通/开放信息")

        state.evidence = all_evidence
        self._sync_tool_traces(state)
        state.structured_result = StructuredResult(
            itinerary=plan.model_dump(),
            places=[{"name": p} for p in places],
        ).model_dump()
        state = await self._run_answer_composition(state, compose_mode="itinerary", plan=plan)
        confidence = self._citation_check(state, [], [], 0.74)
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
        answer_mode = (
            state.answer_mode_decision.answer_mode.value if state.answer_mode_decision else None
        )
        return TravelQueryResponse(
            answer=state.final_response or "",
            structured_result=structured,
            visible_trace=state.visible_trace,
            evidence_summary=evidence_summary,
            field_evidence_summary=state.field_evidence_summary,
            conflicts=[c.model_dump() for c in state.conflicts],
            limitations=state.limitations,
            confidence=confidence,
            citation_check_result=state.citation_check_result.model_dump() if state.citation_check_result else None,
            tool_traces=[t.model_dump() for t in state.tool_traces],
            session_id=state.session_id,
            query_id=state.query_id,
            semantic_frame_summary=self._semantic_frame_summary(state),
            answer_mode=answer_mode,
        )
