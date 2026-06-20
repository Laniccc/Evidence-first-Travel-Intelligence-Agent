from uuid import uuid4

from app.agents.composer_agent import ComposerAgent, ItineraryAgent
from app.agents.intent_agent import IntentAgent, RegionGateAgent
from app.agents.place_research_agent import PlaceResearchAgent
from app.agents.review_mining_agent import ReviewAspectMiningAgent, VerifierAgent
from app.agents.suitability_scorer import TravelSuitabilityScorer
from app.llm_client import LLMClient
from app.orchestrator.citation_check import CitationChecker
from app.orchestrator.evidence_aggregator import EvidenceAggregator
from app.orchestrator.policies import SourceSelectionPolicy
from app.orchestrator.trace import TraceRecorder
from app.schemas.evidence import Evidence
from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.response import StructuredResult, TravelQueryResponse
from app.schemas.review import ReviewAspectResult
from app.schemas.user_query import ConflictRecord, IntentType, TravelAgentState, UserContext, UserGoal
from app.tools import ToolRegistry
from app.tools.mock_data import PLACE_REGISTRY, get_place_location, normalize_place_name


class TravelAgentStateMachine:
    def __init__(self) -> None:
        self.tools = ToolRegistry()
        self.llm = LLMClient()
        self.place_research = PlaceResearchAgent(self.tools)
        self.review_agent = ReviewAspectMiningAgent(self.tools)
        self.scorer = TravelSuitabilityScorer()
        self.verifier = VerifierAgent()
        self.aggregator = EvidenceAggregator()

    async def run(self, query: str, user_context: dict | None = None, session_id: str | None = None) -> TravelQueryResponse:
        ctx = UserContext.model_validate(user_context or {})
        state = TravelAgentState(
            session_id=session_id or str(uuid4()),
            query_id=str(uuid4()),
            raw_user_query=query,
        )

        state.region_gate = RegionGateAgent.run(query)
        TraceRecorder.add(state, f"✓ 识别目的地区域：{state.region_gate.country or '未知'}")
        if not state.region_gate.supported:
            return self._unsupported(state)

        state.user_goal = await IntentAgent.run(query, self.llm, ctx)
        TraceRecorder.add(state, f"✓ 识别意图：{state.user_goal.intent_type.value}")

        self._complete_context(state, ctx)
        TraceRecorder.add(state, f"✓ 识别用户画像：{', '.join(p.value for p in state.user_goal.party) or '一般游客'}")

        state.query_plan = PlaceResearchAgent.build_query_plan(state.user_goal)
        tool_names = SourceSelectionPolicy.select_tools(state.user_goal)
        TraceRecorder.add(state, f"✓ 生成检索计划（工具：{', '.join(tool_names)}）")

        intent = state.user_goal.intent_type
        if intent == IntentType.COMPARE_PLACES:
            return await self._run_compare(state, tool_names)
        if intent == IntentType.ITINERARY:
            return await self._run_itinerary(state, tool_names)
        return await self._run_single(state, tool_names)

    def _backfill_location_from_places(self, goal: UserGoal) -> None:
        for place in goal.place_candidates:
            loc = get_place_location(place)
            if loc:
                goal.destination_country, goal.destination_city = loc
                return

    def _complete_context(self, state: TravelAgentState, ctx: UserContext) -> None:
        goal = state.user_goal
        if not goal:
            return
        if ctx.travel_date:
            goal.travel_date = ctx.travel_date
        if ctx.party:
            goal.party = ctx.party
        if ctx.start_location:
            goal.start_location = ctx.start_location
        if not goal.place_candidates:
            maybe = normalize_place_name(state.raw_user_query)
            if maybe:
                goal.place_candidates = [maybe]
        self._backfill_location_from_places(goal)
        if not goal.destination_city and state.region_gate and state.region_gate.city:
            goal.destination_city = state.region_gate.city
        if not goal.destination_country and state.region_gate and state.region_gate.country:
            goal.destination_country = state.region_gate.country

        assumptions = []
        if not goal.travel_date:
            assumptions.append("未提供出行日期，天气评估使用默认近日假设。")
        if not goal.party:
            assumptions.append("未提供同行人画像，按一般游客评估。")
        state.limitations.extend(assumptions)

    async def _run_single(self, state: TravelAgentState, tool_names: list[str]) -> TravelQueryResponse:
        goal = state.user_goal
        place = goal.place_candidates[0] if goal and goal.place_candidates else None
        if not place:
            state.limitations.append("未能识别具体景点，返回区域级有限建议。")
            state.final_response = "请提供具体景点名称，以便生成证据驱动的情报卡。"
            return self._to_response(state, 0.2)

        canonical = normalize_place_name(place) or place
        self._backfill_location_from_places(goal)
        if canonical not in PLACE_REGISTRY:
            state.limitations.append(f"{place} 暂无结构化 mock 数据，部分结论可能不完整。")

        evidence = await self.place_research.retrieve_for_place(canonical, goal, tool_names)
        state.evidence = evidence
        TraceRecorder.add(state, "✓ 查询官方/地图/交通/评价/天气证据")

        issues = self.verifier.validate(evidence)
        state.limitations.extend(issues)
        conflicts = self.verifier.detect_conflicts(evidence)
        state.conflicts = [ConflictRecord(**c) for c in conflicts]
        if conflicts:
            TraceRecorder.add(state, "✓ 发现来源冲突，已优先采用官方信息")

        fact_sheet = self.aggregator.aggregate(canonical, evidence, state.conflicts)
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

        ranked_data: list[tuple[str, object, ReviewAspectResult, PlaceFactSheet]] = []
        all_evidence: list[Evidence] = []
        compare_tools = [t for t in tool_names if t != "weather"]

        for place in places[:4]:
            canonical = normalize_place_name(place) or place
            self._backfill_location_from_places(goal)
            ev = await self.place_research.retrieve_for_place(canonical, goal, compare_tools)
            all_evidence.extend(ev)
            conflicts = [ConflictRecord(**c) for c in self.verifier.detect_conflicts(ev)]
            fact_sheet = self.aggregator.aggregate(canonical, ev, conflicts)
            review = await self.review_agent.run(canonical, goal)
            rec = self.scorer.score_place(canonical, fact_sheet, review, goal, conflicts)
            ranked_data.append((canonical, rec, review, fact_sheet))
            TraceRecorder.add(state, f"✓ 已完成 {canonical} 情报检索与评分")

        if goal.destination_city and goal.destination_country:
            all_evidence.extend(
                await self.tools.weather.run(
                    city=goal.destination_city,
                    country=goal.destination_country,
                    travel_date=goal.travel_date,
                )
            )

        ranked = sorted(ranked_data, key=lambda x: x[1].overall_score, reverse=True)
        rows = ComposerAgent.build_comparison_rows(ranked)
        state.evidence = all_evidence
        state.conflicts = [ConflictRecord(**c) for c in self.verifier.detect_conflicts(all_evidence)]
        state.structured_result = StructuredResult(
            comparison=[r.model_dump() for r in rows],
            places=[{"name": n, "fact_sheet": fs.model_dump()} for n, _, _, fs in ranked],
        ).model_dump()
        state.final_response = ComposerAgent.compose_compare(ranked, state)

        fact_sheets = [fs for _, _, _, fs in ranked]
        reviews = [r for _, _, r, _ in ranked]
        top_conf = ranked[0][1].confidence if ranked else 0.5
        confidence = self._citation_check(state, fact_sheets, reviews, top_conf)
        return self._to_response(state, confidence)

    async def _run_itinerary(self, state: TravelAgentState, tool_names: list[str]) -> TravelQueryResponse:
        goal = state.user_goal
        self._backfill_location_from_places(goal)
        plan = ItineraryAgent.build(goal)
        places = [i.place_name for i in plan.items if i.place_name]
        all_evidence: list[Evidence] = []
        itinerary_tools = [t for t in tool_names if t not in {"lodging"}]

        for place in places:
            canonical = normalize_place_name(place) or place
            all_evidence.extend(await self.place_research.retrieve_for_place(canonical, goal, itinerary_tools))
            TraceRecorder.add(state, f"✓ 检索 {canonical} 交通/开放信息")

        if goal and goal.destination_city and goal.destination_country and "weather" in tool_names:
            all_evidence.extend(
                await self.tools.weather.run(
                    city=goal.destination_city,
                    country=goal.destination_country,
                    travel_date=goal.travel_date,
                )
            )
            TraceRecorder.add(state, "✓ 检查天气风险")

        state.evidence = all_evidence
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
        confidence, extra_limits = CitationChecker.check(
            state.final_response or "",
            fact_sheets,
            review_results,
            base_confidence,
        )
        state.limitations.extend(extra_limits)
        TraceRecorder.add(state, "✓ 完成引用与限制检查")
        return confidence

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
        ]
        structured = StructuredResult.model_validate(state.structured_result or {})
        return TravelQueryResponse(
            answer=state.final_response or "",
            structured_result=structured,
            visible_trace=state.visible_trace,
            evidence_summary=evidence_summary,
            conflicts=[c.model_dump() for c in state.conflicts],
            limitations=state.limitations,
            confidence=confidence,
            session_id=state.session_id,
            query_id=state.query_id,
        )
