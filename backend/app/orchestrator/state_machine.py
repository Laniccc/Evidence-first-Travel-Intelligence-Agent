from uuid import uuid4

from app.agents.composer_agent import ComposerAgent, ItineraryAgent
from app.agents.intent_agent import IntentAgent, RegionGateAgent
from app.agents.place_research_agent import PlaceResearchAgent
from app.agents.review_mining_agent import ReviewAspectMiningAgent, VerifierAgent
from app.agents.suitability_scorer import TravelSuitabilityScorer
from app.llm_client import LLMClient
from app.orchestrator.confidence import ConfidenceCalculator
from app.orchestrator.trace import TraceRecorder
from app.schemas.evidence import Evidence
from app.schemas.response import RecommendationResult, StructuredResult, TravelQueryResponse
from app.schemas.user_query import ConflictRecord, IntentType, TravelAgentState, UserContext, UserGoal
from app.tools import ToolRegistry
from app.tools.mock_data import PLACE_REGISTRY, normalize_place_name


class TravelAgentStateMachine:
    def __init__(self) -> None:
        self.tools = ToolRegistry()
        self.llm = LLMClient()
        self.place_research = PlaceResearchAgent(self.tools)
        self.review_agent = ReviewAspectMiningAgent(self.tools)
        self.scorer = TravelSuitabilityScorer()
        self.verifier = VerifierAgent()

    async def run(self, query: str, user_context: dict | None = None, session_id: str | None = None) -> TravelQueryResponse:
        ctx = UserContext.model_validate(user_context or {})
        state = TravelAgentState(
            session_id=session_id or str(uuid4()),
            query_id=str(uuid4()),
            raw_user_query=query,
        )

        # S0 Region Gate
        state.region_gate = RegionGateAgent.run(query)
        TraceRecorder.add(state, f"✓ 识别目的地区域：{state.region_gate.country or '未知'}")
        if not state.region_gate.supported:
            return self._unsupported(state)

        # S1 Intent Parsing
        state.user_goal = await IntentAgent.run(query, self.llm, ctx)
        TraceRecorder.add(state, f"✓ 识别意图：{state.user_goal.intent_type.value}")

        # S2 User Context Completion
        self._complete_context(state, ctx)
        TraceRecorder.add(state, f"✓ 识别用户画像：{', '.join(p.value for p in state.user_goal.party) or '一般游客'}")

        # S3 Query Planning
        state.query_plan = PlaceResearchAgent.build_query_plan(state.user_goal)
        TraceRecorder.add(state, "✓ 生成检索计划")

        intent = state.user_goal.intent_type
        if intent == IntentType.COMPARE_PLACES:
            return await self._run_compare(state)
        if intent == IntentType.ITINERARY:
            return await self._run_itinerary(state)
        return await self._run_single(state)

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
        if not goal.destination_city and state.region_gate and state.region_gate.city:
            goal.destination_city = state.region_gate.city
        if not goal.place_candidates:
            maybe = normalize_place_name(state.raw_user_query)
            if maybe:
                goal.place_candidates = [maybe]
        assumptions = []
        if not goal.travel_date:
            assumptions.append("未提供出行日期，天气评估使用默认近日假设。")
        if not goal.party:
            assumptions.append("未提供同行人画像，按一般游客评估。")
        state.limitations.extend(assumptions)

    async def _run_single(self, state: TravelAgentState) -> TravelQueryResponse:
        goal = state.user_goal
        place = goal.place_candidates[0] if goal and goal.place_candidates else None
        if not place:
            state.limitations.append("未能识别具体景点，返回区域级有限建议。")
            state.final_response = "请提供具体景点名称，以便生成证据驱动的情报卡。"
            return self._to_response(state, 0.2)

        canonical = normalize_place_name(place) or place
        if canonical not in PLACE_REGISTRY:
            state.limitations.append(f"{place} 暂无结构化 mock 数据，部分结论可能不完整。")

        # S4-S5 retrieval
        evidence = await self.place_research.retrieve_for_place(canonical, goal)
        state.evidence = evidence
        TraceRecorder.add(state, "✓ 查询官方/地图/交通/评价/天气证据")

        # S6-S8 validation
        issues = self.verifier.validate(evidence)
        state.limitations.extend(issues)
        conflicts = self.verifier.detect_conflicts(evidence)
        state.conflicts = [ConflictRecord(**c) for c in conflicts]
        if conflicts:
            TraceRecorder.add(state, "✓ 发现来源冲突，已优先采用官方信息")

        # S9 review mining
        review_result = await self.review_agent.run(canonical, goal)
        state.review_aspects.append(review_result.model_dump())
        TraceRecorder.add(state, "✓ 完成评价维度抽取")

        # S10 scoring
        recommendation = self.scorer.score_place(canonical, review_result, goal)
        state.scores.overall_suitability = recommendation.overall_score
        state.scores.confidence = recommendation.confidence
        TraceRecorder.add(state, "✓ 完成画像适配评分")

        # S11-S12 compose + checks
        state.final_response = ComposerAgent.compose_single(canonical, recommendation, review_result, state)
        state.structured_result = StructuredResult(recommendation=recommendation, places=[{"name": canonical}]).model_dump()
        self._citation_check(state)
        return self._to_response(state, recommendation.confidence)

    async def _run_compare(self, state: TravelAgentState) -> TravelQueryResponse:
        goal = state.user_goal
        places = goal.place_candidates if goal else []
        if len(places) < 2:
            state.limitations.append("比较任务需要至少两个景点。")
        ranked_data = []
        all_evidence: list[Evidence] = []
        for place in places[:4]:
            canonical = normalize_place_name(place) or place
            ev = await self.place_research.retrieve_for_place(canonical, goal)
            all_evidence.extend(ev)
            review = await self.review_agent.run(canonical, goal)
            rec = self.scorer.score_place(canonical, review, goal)
            ranked_data.append((canonical, rec, review))
            TraceRecorder.add(state, f"✓ 已完成 {canonical} 情报检索与评分")

        ranked = TravelSuitabilityScorer.compare(ranked_data, goal)
        rows = ComposerAgent.build_comparison_rows(ranked)
        state.evidence = all_evidence
        state.conflicts = [ConflictRecord(**c) for c in self.verifier.detect_conflicts(all_evidence)]
        state.structured_result = StructuredResult(
            comparison=[r.model_dump() for r in rows],
            places=[{"name": n} for n, _, _ in ranked],
        ).model_dump()
        state.final_response = ComposerAgent.compose_compare(ranked, state)
        self._citation_check(state)
        top_conf = ranked[0][1].confidence if ranked else 0.5
        return self._to_response(state, top_conf)

    async def _run_itinerary(self, state: TravelAgentState) -> TravelQueryResponse:
        goal = state.user_goal
        plan = ItineraryAgent.build(goal)
        places = [i.place_name for i in plan.items if i.place_name]
        all_evidence: list[Evidence] = []
        for place in places:
            canonical = normalize_place_name(place) or place
            all_evidence.extend(await self.place_research.retrieve_for_place(canonical, goal))
            TraceRecorder.add(state, f"✓ 检索 {canonical} 交通/开放信息")
        if goal and goal.destination_city and goal.destination_country:
            all_evidence.extend(
                await self.tools.weather.run(city=goal.destination_city, country=goal.destination_country, travel_date=goal.travel_date)
            )
            TraceRecorder.add(state, "✓ 检查天气风险")
        state.evidence = all_evidence
        state.structured_result = StructuredResult(itinerary=plan.model_dump(), places=[{"name": p} for p in places]).model_dump()
        state.final_response = ComposerAgent.compose_itinerary(plan, state)
        self._citation_check(state)
        return self._to_response(state, 0.74)

    def _unsupported(self, state: TravelAgentState) -> TravelQueryResponse:
        state.final_response = (
            "当前版本重点支持日本、中国、韩国。\n"
            "您的查询暂未落在重点支持范围内，可先告知具体国家/城市/景点，或等待后续版本扩展。"
        )
        state.limitations.append(state.region_gate.reason if state.region_gate else "Unsupported region")
        return self._to_response(state, 0.3)

    def _citation_check(self, state: TravelAgentState) -> None:
        if not state.evidence:
            state.limitations.append("关键证据不足，部分结论置信度受限。")
        TraceRecorder.add(state, "✓ 完成引用与限制检查")

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
