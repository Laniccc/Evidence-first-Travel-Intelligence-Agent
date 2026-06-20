from uuid import uuid4

from app.agents.composer_agent import ComposerAgent, ItineraryAgent
from app.agents.information_need_planner import InformationNeedPlanner
from app.agents.intent_agent import IntentAgent, RegionGateAgent
from app.agents.place_research_agent import PlaceResearchAgent
from app.agents.review_mining_agent import ReviewAspectMiningAgent, VerifierAgent
from app.agents.suitability_scorer import TravelSuitabilityScorer
from app.agents.travel_task_to_user_goal_adapter import SUPPORTED_REGIONS, TravelTaskToUserGoalAdapter
from app.catalog.place_catalog import get_place_catalog
from app.llm_client import LLMClient
from app.orchestrator.citation_check import CitationChecker
from app.orchestrator.evidence_aggregator import EvidenceAggregator
from app.orchestrator.states.query_understanding_state import QueryUnderstandingPromptState
from app.orchestrator.trace import TraceRecorder
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.evidence import Evidence
from app.schemas.place_context import PlaceContext
from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.response import StructuredResult, TravelQueryResponse
from app.schemas.review import ReviewAspectResult
from app.schemas.travel_task import TravelTaskType
from app.schemas.user_query import ConflictRecord, IntentType, RegionGateResult, TravelAgentState, UserContext, UserGoal
from app.tools import ToolRegistry
from app.tools.tool_router import ToolRouter


class TravelAgentStateMachine:
    def __init__(self) -> None:
        self.tools = ToolRegistry()
        self.llm = LLMClient()
        self.place_research = PlaceResearchAgent(self.tools)
        self.review_agent = ReviewAspectMiningAgent(self.tools)
        self.scorer = TravelSuitabilityScorer()
        self.verifier = VerifierAgent()
        self.aggregator = EvidenceAggregator()
        self.catalog = get_place_catalog()
        self.tool_router = ToolRouter()
        self.query_understanding_state = QueryUnderstandingPromptState(self.llm)

    async def run(self, query: str, user_context: dict | None = None, session_id: str | None = None) -> TravelQueryResponse:
        ctx = UserContext.model_validate(user_context or {})
        memory = ConversationMemory.from_user_context(user_context)
        state = TravelAgentState(
            session_id=session_id or str(uuid4()),
            query_id=str(uuid4()),
            raw_user_query=query,
            conversation_memory=memory,
        )

        state = await self.query_understanding_state.run(state, ctx, user_context)
        if state.next_state == "clarification_response":
            confidence = state.query_understanding.confidence if state.query_understanding else 0.3
            return self._to_response(state, confidence)

        gate_query = state.rewritten_query_result.rewritten_query if state.rewritten_query_result else query
        state.region_gate = self._resolve_region_gate(state, query, gate_query, memory)
        TraceRecorder.add(state, f"✓ 识别目的地区域：{state.region_gate.country or '未知'}")
        if not state.region_gate.supported:
            return self._unsupported(state)

        qu_confidence = state.query_understanding.confidence if state.query_understanding else 0.0
        if TravelTaskToUserGoalAdapter.should_use_task(
            state.travel_task,
            state.query_understanding,
            qu_confidence,
        ):
            state.user_goal = TravelTaskToUserGoalAdapter.to_user_goal(state.travel_task, ctx)
            TraceRecorder.add(state, f"✓ 已从 TravelTask 生成 UserGoal：{state.user_goal.intent_type.value}")
        else:
            state.user_goal = await IntentAgent.run(gate_query, self.llm, ctx)
            TraceRecorder.add(state, f"✓ IntentAgent fallback：{state.user_goal.intent_type.value}")

        self._complete_context(state, ctx)
        TraceRecorder.add(state, f"✓ 识别用户画像：{', '.join(p.value for p in state.user_goal.party) or '一般游客'}")

        if not state.travel_task:
            state.limitations.append("TravelTask 缺失，后续路由可能受限。")
            return self._to_response(state, 0.25)

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

        state.query_plan = PlaceResearchAgent.build_query_plan(state.user_goal)
        if state.tool_execution_plan.unsupported_needs:
            state.limitations.append(
                "以下信息需求暂无直接工具支撑：" + ", ".join(state.tool_execution_plan.unsupported_needs)
            )

        task_type = state.travel_task.task_type
        if task_type == TravelTaskType.COMPARE_PLACES:
            return await self._run_compare(state, tool_names)
        if task_type == TravelTaskType.ITINERARY_PLANNING:
            return await self._run_itinerary(state, tool_names)
        if task_type == TravelTaskType.CROWD_INQUIRY:
            return await self._run_crowd_inquiry(state, tool_names)
        return await self._run_single(state, tool_names)

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

        if not region.supported and state.rewritten_query_result:
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

        if not region.supported:
            for place in self.catalog.find_places_in_text(gate_query) or self.catalog.find_places_in_text(raw_query):
                loc = self.catalog.get_place_location(place)
                if loc:
                    return RegionGateResult(
                        supported=True,
                        country=loc.country,
                        city=loc.city,
                        reason=f"Resolved from place catalog: {place}",
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

    async def _run_crowd_inquiry(self, state: TravelAgentState, tool_names: list[str]) -> TravelQueryResponse:
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
        evidence = await self.place_research.retrieve_for_place(
            canonical, goal, tool_names, place_ctx, state.tool_execution_plan
        )
        state.evidence = evidence
        state.tool_traces = list(self.tools.traces)

        fact_sheet = self.aggregator.aggregate(canonical, evidence, [])
        self._collect_field_summary(state, [fact_sheet])
        review_result = await self.review_agent.run(canonical, goal)
        recommendation = self.scorer.score_place(canonical, fact_sheet, review_result, goal, [])

        state.final_response = ComposerAgent.compose_crowd_inquiry(canonical, fact_sheet, review_result, state)
        state.structured_result = StructuredResult(
            recommendation=recommendation,
            places=[{"name": canonical, "fact_sheet": fact_sheet.model_dump()}],
        ).model_dump()

        confidence = self._citation_check(state, [fact_sheet], [review_result], min(recommendation.confidence, 0.75))
        return self._to_response(state, confidence)

    async def _run_single(self, state: TravelAgentState, tool_names: list[str]) -> TravelQueryResponse:
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
        evidence = await self.place_research.retrieve_for_place(
            canonical, goal, tool_names, place_ctx, state.tool_execution_plan
        )
        state.evidence = evidence
        state.tool_traces = list(self.tools.traces)
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

        state.final_response = ComposerAgent.compose_single(canonical, recommendation, review_result, fact_sheet, state)
        state.structured_result = StructuredResult(
            recommendation=recommendation,
            places=[{"name": canonical, "fact_sheet": fact_sheet.model_dump()}],
        ).model_dump()

        confidence = self._citation_check(state, [fact_sheet], [review_result], recommendation.confidence)
        return self._to_response(state, confidence)

    async def _run_compare(self, state: TravelAgentState, tool_names: list[str]) -> TravelQueryResponse:
        goal = state.user_goal
        places = goal.place_candidates if goal else []
        if len(places) < 2:
            state.limitations.append("比较任务需要至少两个景点。")

        self._backfill_location_from_places(state)
        ranked_data: list[tuple[str, object, ReviewAspectResult, PlaceFactSheet]] = []
        all_evidence: list[Evidence] = []
        base_tools = [t for t in tool_names if t not in {"weather", "lodging"}]

        for idx, place in enumerate(places[:4]):
            canonical = self.catalog.normalize_place_name(place) or place
            place_ctx = self._place_context_for(state, place, idx)
            place_tools = list(base_tools)
            if "weather" in tool_names and place_ctx.country and place_ctx.city:
                place_tools.append("weather")
            ev = await self.place_research.retrieve_for_place(
                canonical, goal, place_tools, place_ctx, state.tool_execution_plan
            )
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
        state.tool_traces = list(self.tools.traces)
        state.conflicts = [ConflictRecord(**c) for c in self.verifier.detect_conflicts(all_evidence)]
        fact_sheets = [fs for _, _, _, fs in ranked]
        self._collect_field_summary(state, fact_sheets)
        state.structured_result = StructuredResult(
            comparison=[r.model_dump() for r in rows],
            places=[{"name": n, "fact_sheet": fs.model_dump()} for n, _, _, fs in ranked],
        ).model_dump()
        state.final_response = ComposerAgent.compose_compare(ranked, state)

        reviews = [r for _, _, r, _ in ranked]
        top_conf = ranked[0][1].confidence if ranked else 0.5
        confidence = self._citation_check(state, fact_sheets, reviews, top_conf)
        return self._to_response(state, confidence)

    async def _run_itinerary(self, state: TravelAgentState, tool_names: list[str]) -> TravelQueryResponse:
        goal = state.user_goal
        self._backfill_location_from_places(state)
        plan = ItineraryAgent.build(goal)
        places = [i.place_name for i in plan.items if i.place_name]
        all_evidence: list[Evidence] = []
        itinerary_tools = [t for t in tool_names if t not in {"lodging"}]

        for idx, place in enumerate(places):
            canonical = self.catalog.normalize_place_name(place) or place
            place_ctx = self._place_context_for(state, place, idx)
            all_evidence.extend(
                await self.place_research.retrieve_for_place(
                    canonical, goal, itinerary_tools, place_ctx, state.tool_execution_plan
                )
            )
            TraceRecorder.add(state, f"✓ 检索 {canonical} 交通/开放信息")

        if goal and goal.destination_city and goal.destination_country and "weather" in tool_names:
            all_evidence.extend(
                await self.tools.run_tool(
                    "weather",
                    city=goal.destination_city,
                    country=goal.destination_country,
                    travel_date=goal.travel_date,
                )
            )
            TraceRecorder.add(state, "✓ 检查天气风险")

        state.evidence = all_evidence
        state.tool_traces = list(self.tools.traces)
        state.structured_result = StructuredResult(
            itinerary=plan.model_dump(),
            places=[{"name": p} for p in places],
        ).model_dump()
        state.final_response = ComposerAgent.compose_itinerary(plan, state)
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

    def _to_response(self, state: TravelAgentState, confidence: float) -> TravelQueryResponse:
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
        )
