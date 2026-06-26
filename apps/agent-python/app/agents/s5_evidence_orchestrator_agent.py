"""S5 LLM orchestrator: plan → delegate sub-agent → review → finish (no direct CALL_TOOL)."""

from __future__ import annotations

import json
import logging
import uuid

from app.agents.s5_subagent_registry import ORCHESTRATOR_SUBAGENT_NAMES, subagent_definitions_for_prompt
from app.config import get_settings
from app.llm_client import LLMClient
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.evidence_signal_utils import is_day_trip_query
from app.orchestrator.information_need_aliases import nearby_needs_set
from app.orchestrator.place_disambiguation_guard import disambiguation_pending_without_city
from app.schemas.intent_profile import PrimaryIntent
from app.orchestrator.search_query_rewriter import SearchQueryRewriter
from app.schemas.user_query import TravelAgentState
from app.utils.llm_json import parse_llm_json

logger = logging.getLogger(__name__)

_SYSTEM = """You are the S5 evidence-planning orchestrator for a China travel agent.
Return ONLY one JSON object per step (AgentAction schema):
{
  "action_type": "call_subagent" | "finish_state",
  "target": "<subagent_name>",
  "arguments": { ... delegated task fields ... },
  "reason_summary": "...",
  "confidence": 0.0-1.0
}

Your THREE roles each step:
1. PLAN — understand user need; craft lookup_intent + search_query + anchor_keywords + tool_parameters.
2. DELEGATE — CALL_SUBAGENT only (never call MCP tools directly).
3. REVIEW — read subagent_results / evidence_highlights; if user purpose met → finish_state.

Available subagents (see subagent_definitions):
- entity_resolution_agent: anchor place/POI, resolve 同名地点 (Baidu geo inside agent).
- route_feasibility_agent: distance/duration/traffic (Baidu route inside agent).
- fact_lookup_agent: phase/source_family runner for LOOKUP (official_discovery, fact_acquisition).
- fact_search_agent: fallback web search when fact_lookup insufficient.
- weather_context_agent: short-term weather when need forecast/weather.
- evidence_contradiction_decomposer_agent: split conflicting claim tiers.

Delegation arguments (pass in "arguments"):
- lookup_intent, claim_target, search_query, anchor_keywords, information_need
- tool_parameters: {origin, destination, region, mode, ...} when needed
- task_id: optional

Ordering heuristics:
- China place without city → entity_resolution_agent before route/fact.
- 一天够吗/多远/多久 → route_feasibility_agent (needs origin+destination in tool_parameters).
- ticket/opening_hours/elevation → LookupResearchChain: entity_resolution_agent if unanchored;
  then fact_lookup_agent per phase+source_family; fact_search_agent only when audit says continue.
- place_candidates ambiguous → entity_resolution_agent (handles branch searches internally).
- multi-value conflict → evidence_contradiction_decomposer_agent.

finish_state when: coverage_report shows required claims covered, OR subagent_results show
sufficient evidence for primary_information_need, OR no productive subagent left.

Do NOT output user-facing answer text."""

_REPAIR = "\n\nReturn ONLY valid JSON matching the schema above."


class S5EvidenceOrchestratorAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or LLMClient()

    async def next_action(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        from app.orchestrator.lookup_research_chain import advance_entity_anchor_if_satisfied

        advance_entity_anchor_if_satisfied(state)
        poi_action = self._mandatory_poi_entity_action(state, step)
        if poi_action is not None:
            return poi_action

        fact_action = self._mandatory_lookup_entity_action(state, step)
        if fact_action is not None:
            return fact_action

        if self.llm and self.llm._should_use_anthropic():
            try:
                return await self._llm_next_action(state, prompt_context, step)
            except Exception as exc:
                logger.warning("S5 orchestrator LLM failed, using fallback: %s", exc)
        return self._deterministic_fallback(state, prompt_context, step)

    def _mandatory_poi_entity_action(self, state: TravelAgentState, step: int) -> AgentAction | None:
        """Nearby-style task classes: force entity_resolution before LLM/fallback retrieval."""
        from app.orchestrator.s5_poi_anchor_policy import (
            build_entity_resolution_arguments,
            mandatory_poi_entity_required,
        )

        if step >= 8 or not mandatory_poi_entity_required(state):
            return None
        args = build_entity_resolution_arguments(state)
        place = args.get("search_query") or "place"
        return self._subagent_action(
            "entity_resolution_agent",
            args,
            f"POI anchor gate (nearby task): resolve {place}",
        )

    def _mandatory_lookup_entity_action(self, state: TravelAgentState, step: int) -> AgentAction | None:
        """LOOKUP: force entity_resolution when entity_anchor phase incomplete."""
        from app.orchestrator.fact_lookup_policy import is_fact_lookup_task
        from app.orchestrator.lookup_research_chain import lookup_mandatory_entity_anchor
        from app.orchestrator.s5_poi_anchor_policy import build_entity_resolution_arguments

        if not is_fact_lookup_task(state) or not lookup_mandatory_entity_anchor(state, step):
            return None
        args = build_entity_resolution_arguments(state)
        place = args.get("search_query") or "place"
        return self._subagent_action(
            "entity_resolution_agent",
            args,
            f"Lookup chain entity_anchor: resolve {place}",
        )

    async def _llm_next_action(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        ctx = ClaimSearchPlanner.planning_context(state)
        payload = {
            "step": step + 1,
            "raw_query": state.raw_user_query,
            "primary_information_need": ctx.get("primary_information_need"),
            "claim_types": ctx.get("claim_types"),
            "entities": ctx.get("entities"),
            "place_candidates": ctx.get("place_candidates"),
            "place_disambiguation_pending": disambiguation_pending_without_city(state),
            "subagent_definitions": subagent_definitions_for_prompt(),
            "subagent_results": (state.structured_result or {}).get("subagent_results", [])[-6:],
            "evidence_highlights": ctx.get("evidence_highlights"),
            "coverage_report": (
                state.coverage_report.model_dump() if state.coverage_report else None
            ),
            "keyword_search_count": ctx.get("keyword_search_count"),
            "tools_called": [t.tool_name for t in state.tool_traces],
            "query_rewrite_plan": ctx.get("query_rewrite_plan"),
            "user_need_residual": ctx.get("user_need_residual"),
        }
        from app.orchestrator.nearby_task_orchestration import (
            nearby_s5_planning_context,
            nearby_s5_system_append,
        )
        from app.orchestrator.fact_lookup_task_orchestration import (
            fact_s5_planning_context,
            fact_s5_system_append,
        )

        payload.update(nearby_s5_planning_context(state))
        payload.update(fact_s5_planning_context(state))
        chain_ctx = payload.get("lookup_research_chain")
        if chain_ctx:
            payload["completed_phases"] = chain_ctx.get("completed_phases")
            payload["query_objectives"] = chain_ctx.get("query_objectives")
        system = _SYSTEM
        nearby_append = nearby_s5_system_append(state)
        fact_append = fact_s5_system_append(state)
        for block in (nearby_append, fact_append):
            if block:
                system = f"{system}\n\n{block}"
        raw = await self.llm.complete(
            system=system,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            max_tokens=get_settings().llm_planner_max_tokens,
            json_only=True,
        )
        data = parse_llm_json(raw)
        if not data:
            raise ValueError("orchestrator returned empty JSON")
        action = self._coerce_action(data, state)
        if action.action_type == AgentActionType.CALL_SUBAGENT:
            if action.target not in ORCHESTRATOR_SUBAGENT_NAMES:
                raise ValueError(f"unknown subagent {action.target!r}")
            action = self._gate_lookup_entity_resolution(state, action, step)
        return action

    def _deterministic_fallback(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        structured = state.structured_result or {}
        done_subagents = {r.get("subagent") for r in structured.get("subagent_results", [])}
        frame = state.semantic_frame
        need = ClaimSearchPlanner.primary_information_need(state)
        ctx = ClaimSearchPlanner.planning_context(state)
        strategy = state.intent_strategy

        if self._should_finish(state, prompt_context, step):
            args: dict = {}
            from app.orchestrator.fact_lookup_policy import is_fact_lookup_task, primary_fact_need_from_state
            from app.orchestrator.ticket_lookup_policy import ticket_lookup_retrieval_complete

            if (
                is_fact_lookup_task(state)
                and primary_fact_need_from_state(state) == "ticket_price"
                and ticket_lookup_retrieval_complete(state)
            ):
                args["evidence_gap_acknowledged"] = True
            return AgentAction(
                action_type=AgentActionType.FINISH_STATE,
                arguments=args,
                reason_summary="S5 orchestrator: evidence sufficient or step budget",
                confidence=0.78,
            )

        intent_action = self._intent_subagent_action(
            state, frame, need, ctx, done_subagents, step, strategy
        )
        if intent_action is not None:
            return intent_action

        lookup_action = self._lookup_chain_fallback_action(state, step)
        if lookup_action is not None:
            return lookup_action

        country = ""
        if frame and frame.entities:
            country = (frame.entities.country or "").strip().lower()
        is_china = country in ("china", "中国", "")
        has_place = bool(frame and frame.entities and frame.entities.places)
        city = (frame.entities.city or "").strip() if frame and frame.entities else ""

        if (
            is_china
            and has_place
            and (not city or disambiguation_pending_without_city(state))
            and "entity_resolution_agent" not in done_subagents
            and step < 8
        ):
            from app.orchestrator.fact_lookup_policy import is_fact_lookup_task
            from app.orchestrator.lookup_entity_resolution_policy import (
                entity_resolution_allowed_for_lookup,
            )

            if is_fact_lookup_task(state) and not entity_resolution_allowed_for_lookup(state):
                pass
            else:
                place = frame.entities.places[0]
                return self._subagent_action(
                    "entity_resolution_agent",
                    {
                        "lookup_intent": f"锚定用户所指地点：{place}",
                        "claim_target": "entity_resolution",
                        "search_query": place,
                        "anchor_keywords": [place],
                        "information_need": "entity_resolution",
                    },
                    f"Fallback: resolve place {place}",
                )

        route_needs = {
            "route_plan",
            "distance",
            "duration",
            "transport_planning",
            "itinerary_feasibility",
            "transit",
        }
        wants_route = need in route_needs or (frame and is_day_trip_query(frame))
        if wants_route and "route_feasibility_agent" not in done_subagents:
            params: dict[str, str] = {}
            if frame and frame.entities and frame.entities.places:
                params["destination"] = frame.entities.places[0]
            goal = state.user_goal
            if goal and goal.start_location:
                params["origin"] = goal.start_location
            return self._subagent_action(
                "route_feasibility_agent",
                {
                    "lookup_intent": "获取城际/景区路线距离与时长",
                    "claim_target": need or "route_plan",
                    "information_need": need or "route_plan",
                    "tool_parameters": params,
                    "anchor_keywords": [v for v in params.values() if v],
                    "search_query": " ".join(params.values()) or state.raw_user_query[:64],
                },
                "Fallback: route feasibility",
            )

        weather_needs = {"forecast", "weather", "weather_today", "today_weather"}
        if need in weather_needs and "weather_context_agent" not in done_subagents:
            return self._subagent_action(
                "weather_context_agent",
                {
                    "lookup_intent": "获取短期天气",
                    "claim_target": need,
                    "information_need": need,
                },
                "Fallback: weather context",
            )

        rewriter = SearchQueryRewriter.from_planning_context(ctx, state)
        tasks = rewriter.to_search_tasks(max_tasks=2)
        fact_runs = sum(1 for r in structured.get("subagent_results", []) if r.get("subagent") == "fact_search_agent")
        from app.orchestrator.nearby_task_orchestration import (
            is_nearby_recommendation_task,
            nearby_s5_skip_fact_search,
        )
        from app.orchestrator.fact_lookup_task_orchestration import (
            is_fact_lookup_task,
            fact_s5_skip_fact_search,
        )

        skip_fact = (
            (is_nearby_recommendation_task(state) and nearby_s5_skip_fact_search(state))
            or (is_fact_lookup_task(state) and fact_s5_skip_fact_search(state))
        )
        if not skip_fact:
            if tasks and fact_runs < min(6, int(ctx.get("max_keyword_searches") or 10)):
                task = tasks[fact_runs % len(tasks)]
                return self._subagent_action(
                    "fact_search_agent",
                    task.model_dump(),
                    f"Fallback: fact search {task.search_query[:48]}",
                )

        return AgentAction(
            action_type=AgentActionType.FINISH_STATE,
            reason_summary="S5 orchestrator fallback: no further subagent",
            confidence=0.7,
        )

    def _should_finish(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        step: int,
    ) -> bool:
        from app.orchestrator.nearby_task_orchestration import nearby_s5_may_finish_early
        from app.orchestrator.fact_lookup_task_orchestration import fact_s5_may_finish_early

        if nearby_s5_may_finish_early(state, step) or fact_s5_may_finish_early(state, step):
            return True
        if step >= 25:
            return True
        report = state.coverage_report
        if report and report.all_required_covered:
            return True
        from app.orchestrator.fact_lookup_policy import is_fact_lookup_task, primary_fact_need_from_state
        from app.orchestrator.ticket_lookup_policy import ticket_lookup_retrieval_complete

        if (
            is_fact_lookup_task(state)
            and primary_fact_need_from_state(state) == "ticket_price"
            and ticket_lookup_retrieval_complete(state)
            and step >= 2
        ):
            return True
        structured = state.structured_result or {}
        results = structured.get("subagent_results") or []
        if len(results) >= 8 and step >= 4:
            recent = results[-3:]
            if all(int(r.get("evidence_count") or 0) == 0 for r in recent):
                return True
        max_calls = int(
            prompt_context.get("max_tool_calls") or get_settings().mcp_max_tool_calls_per_state
        )
        if int(prompt_context.get("tool_call_count", 0)) >= max_calls:
            return True
        return False

    def _gate_lookup_entity_resolution(
        self,
        state: TravelAgentState,
        action: AgentAction,
        step: int,
    ) -> AgentAction:
        if action.target != "entity_resolution_agent":
            return action
        from app.orchestrator.fact_lookup_policy import is_fact_lookup_task
        from app.orchestrator.lookup_entity_resolution_policy import entity_resolution_allowed_for_lookup

        if not is_fact_lookup_task(state) or entity_resolution_allowed_for_lookup(state):
            return action
        fallback = self._lookup_chain_fallback_action(state, step)
        return fallback or action

    def _lookup_chain_fallback_action(
        self,
        state: TravelAgentState,
        step: int,
    ) -> AgentAction | None:
        from app.orchestrator.fact_lookup_policy import is_fact_lookup_task, primary_fact_need_from_state
        from app.orchestrator.lookup_query_objectives import build_lookup_query_objectives
        from app.orchestrator.lookup_research_chain import (
            is_duplicate_lookup_attempt,
            lookup_attempt_signature,
            next_recommended_phase,
            source_families_for_phase,
        )

        if not is_fact_lookup_task(state) or step >= 12:
            return None
        phase = next_recommended_phase(state)
        if not phase or phase in {"research_frame", "source_plan", "retrieval_audit"}:
            return None
        if phase == "entity_anchor":
            return None
        need = primary_fact_need_from_state(state)
        for family in source_families_for_phase(phase, need):
            objectives = build_lookup_query_objectives(state, need, family)
            obj_key = objectives[0].objective if objectives else family
            sig = lookup_attempt_signature(
                subagent="fact_lookup_agent",
                claim_type=need,
                phase=phase,
                source_family=family,
                objective=obj_key,
            )
            if is_duplicate_lookup_attempt(state, sig):
                continue
            return self._subagent_action(
                "fact_lookup_agent",
                {
                    "lookup_phase": phase,
                    "source_family": family,
                    "claim_target": need,
                    "query_objectives": [o.model_dump() for o in objectives],
                },
                f"Lookup chain fallback: {phase}/{family}",
            )
        return None

    def _intent_subagent_action(
        self,
        state: TravelAgentState,
        frame,
        need: str | None,
        ctx: dict,
        done_subagents: set[str],
        step: int,
        strategy,
    ) -> AgentAction | None:
        if not strategy or not strategy.preferred_subagents:
            return None

        primary = strategy.primary_intent
        needs = set(frame.information_needs or []) if frame else set()
        nearby = bool(nearby_needs_set(needs)) or primary == PrimaryIntent.NEARBY

        for agent in strategy.preferred_subagents:
            if agent not in ORCHESTRATOR_SUBAGENT_NAMES:
                continue
            if agent in done_subagents:
                continue

            if agent == "entity_resolution_agent":
                if step >= 8:
                    continue
                from app.orchestrator.fact_lookup_policy import is_fact_lookup_task
                from app.orchestrator.lookup_entity_resolution_policy import (
                    entity_resolution_allowed_for_lookup,
                )

                if is_fact_lookup_task(state) and not entity_resolution_allowed_for_lookup(state):
                    continue
                if not frame or not frame.entities or not frame.entities.places:
                    continue
                place = frame.entities.places[0]
                return self._subagent_action(
                    agent,
                    {
                        "lookup_intent": f"锚定用户所指地点：{place}",
                        "claim_target": "entity_resolution",
                        "search_query": place,
                        "anchor_keywords": [place],
                        "information_need": "entity_resolution",
                    },
                    f"Intent chain: resolve place {place}",
                )

            if agent == "route_feasibility_agent":
                route_needs = {
                    "route_plan",
                    "distance",
                    "duration",
                    "transport_planning",
                    "itinerary_feasibility",
                    "transit",
                }
                wants_route = (
                    need in route_needs
                    or primary == PrimaryIntent.PLANNING
                    or (frame and is_day_trip_query(frame))
                )
                if not wants_route:
                    continue
                params: dict[str, str] = {}
                if frame and frame.entities and frame.entities.places:
                    params["destination"] = frame.entities.places[0]
                goal = state.user_goal
                if goal and goal.start_location:
                    params["origin"] = goal.start_location
                return self._subagent_action(
                    agent,
                    {
                        "lookup_intent": "获取城际/景区路线距离与时长",
                        "claim_target": need or "route_plan",
                        "information_need": need or "route_plan",
                        "tool_parameters": params,
                        "anchor_keywords": [v for v in params.values() if v],
                        "search_query": " ".join(params.values()) or state.raw_user_query[:64],
                    },
                    "Intent chain: route feasibility",
                )

            if agent == "weather_context_agent":
                weather_needs = {"forecast", "weather", "weather_today", "today_weather"}
                wants_weather = need in weather_needs or primary == PrimaryIntent.REALTIME_CHECK
                if not wants_weather:
                    continue
                return self._subagent_action(
                    agent,
                    {
                        "lookup_intent": "获取短期天气",
                        "claim_target": need or "forecast",
                        "information_need": need or "forecast",
                    },
                    "Intent chain: weather context",
                )

            if agent == "fact_search_agent":
                if primary == PrimaryIntent.CLARIFICATION:
                    continue
                from app.orchestrator.nearby_task_orchestration import nearby_s5_skip_fact_search
                from app.orchestrator.fact_lookup_task_orchestration import (
                    is_fact_lookup_task,
                    fact_s5_skip_fact_search,
                )

                if nearby and nearby_s5_skip_fact_search(state):
                    continue
                if is_fact_lookup_task(state) and fact_s5_skip_fact_search(state):
                    continue
                rewriter = SearchQueryRewriter.from_planning_context(ctx, state)
                tasks = rewriter.to_search_tasks(max_tasks=2)
                fact_runs = sum(
                    1
                    for r in (state.structured_result or {}).get("subagent_results", [])
                    if r.get("subagent") == "fact_search_agent"
                )
                if not tasks or fact_runs >= min(6, int(ctx.get("max_keyword_searches") or 10)):
                    continue
                if nearby and fact_runs >= 2 and "entity_resolution_agent" not in done_subagents:
                    continue
                task = tasks[fact_runs % len(tasks)]
                from app.orchestrator.s5_diversified_tool_selector import select_tool_for_subagent

                whitelist = ctx.get("tool_whitelist")
                selection = select_tool_for_subagent(
                    state,
                    task,
                    whitelist,
                    subagent="fact_search_agent",
                )
                task_args = task.model_dump()
                if selection:
                    task_args["preferred_tool"] = selection.tool_name
                    task_args["tool_parameters"] = {
                        **(task_args.get("tool_parameters") or {}),
                        **selection.tool_parameters_patch,
                    }
                return self._subagent_action(
                    agent,
                    task_args,
                    f"Intent chain: fact search {task.search_query[:48]}",
                )

            if agent == "evidence_contradiction_decomposer_agent":
                continue

        return None

    @staticmethod
    def _subagent_action(target: str, arguments: dict, reason: str) -> AgentAction:
        args = dict(arguments)
        args.setdefault("task_id", f"orch-{uuid.uuid4().hex[:8]}")
        return AgentAction(
            action_type=AgentActionType.CALL_SUBAGENT,
            target=target,
            arguments=args,
            reason_summary=reason,
            confidence=0.8,
        )

    @staticmethod
    def _coerce_action(data: dict, state: TravelAgentState) -> AgentAction:
        action_type = str(data.get("action_type") or "").lower().replace("-", "_")
        if action_type in {"finish", "finish_state"}:
            return AgentAction(
                action_type=AgentActionType.FINISH_STATE,
                arguments=data.get("arguments") if isinstance(data.get("arguments"), dict) else {},
                reason_summary=str(data.get("reason_summary") or "Orchestrator finish"),
                confidence=float(data.get("confidence") or 0.8),
            )
        target = str(data.get("target") or "").strip()
        arguments = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
        arguments.setdefault("task_id", f"llm-{uuid.uuid4().hex[:8]}")
        if not arguments.get("search_query") and state.raw_user_query:
            arguments.setdefault("search_query", state.raw_user_query[:96])
        return AgentAction(
            action_type=AgentActionType.CALL_SUBAGENT,
            target=target,
            arguments=arguments,
            reason_summary=str(data.get("reason_summary") or f"Orchestrator → {target}"),
            confidence=float(data.get("confidence") or 0.85),
        )
