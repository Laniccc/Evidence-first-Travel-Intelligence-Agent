"""S5 diversified MCP tool selection: ledger-aware rotation per claim / intent."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.information_need_aliases import (
    is_nearby_need,
    normalize_need,
    query_text_from_state,
    resolve_nearby_need,
)
from app.orchestrator.mcp_tool_arguments import nearby_coordinate_patch
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.s5_tool_attempt_ledger import (
    Phase,
    S5ToolAttemptLedger,
    ToolAttemptRecord,
    get_ledger,
    save_ledger,
)
from app.schemas.search_task import SearchTask
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name
from app.orchestrator.s5_poi_anchor_policy import poi_anchor_satisfied
from tools.mcp.adapters.baidu_response_parser import (
    pick_baidu_uid_from_evidence,
    resolve_coordinates_from_evidence,
    resolve_nearby_anchor_coordinates,
)

RETRIEVAL_TOOL_SEQUENCE: dict[str, list[str]] = {
    "poi_recommendation": [
        "baidu_place_search_mcp",
        "baidu_place_detail_mcp",
        "dianping_nearby_crawler_mcp",
        "dianping_review_crawler_mcp",
        "ctrip_review_crawler_mcp",
        "search_mcp",
        "browser_mcp",
    ],
    "strict_fact_lookup": [
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "browser_mcp",
        "baidu_place_search_mcp",
        "baidu_place_detail_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
        "search_mcp",
    ],
    "geo_fact_lookup": [
        "wikidata_mcp",
        "wikipedia_mcp",
        "search_mcp",
        "browser_mcp",
        "baidu_place_detail_mcp",
        "official_page_reader_mcp",
        "osm_mcp",
    ],
    "live_status": [
        "baidu_weather_mcp",
        "openmeteo_mcp",
        "baidu_traffic_mcp",
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "search_mcp",
    ],
    "multi_place_parallel": [
        "baidu_place_search_mcp",
        "dianping_review_crawler_mcp",
        "ctrip_review_crawler_mcp",
        "baidu_route_mcp",
        "baidu_route_matrix_mcp",
        "search_mcp",
    ],
    "route_first": [
        "baidu_place_search_mcp",
        "baidu_route_mcp",
        "baidu_route_matrix_mcp",
        "baidu_traffic_mcp",
        "search_mcp",
    ],
    "review_first": [
        "dianping_review_crawler_mcp",
        "ctrip_review_crawler_mcp",
        "search_mcp",
        "browser_mcp",
    ],
    "mixed_advisory": [
        "dianping_review_crawler_mcp",
        "ctrip_review_crawler_mcp",
        "search_mcp",
        "climate_mcp",
        "openmeteo_mcp",
        "baidu_route_mcp",
    ],
    "minimal_probe": [
        "baidu_place_search_mcp",
        "baidu_geocode_mcp",
        "search_mcp",
    ],
}

CLAIM_SEQUENCE_OVERRIDE: dict[str, str] = {
    "entity_resolution": "minimal_probe",
    "geo_resolution": "minimal_probe",
    "place_lookup": "minimal_probe",
    "place_candidates": "minimal_probe",
    "nearby_food": "poi_recommendation",
    "nearby_poi": "poi_recommendation",
    "nearby_hotel": "poi_recommendation",
    "nearby_rest_area": "poi_recommendation",
    "nearby_toilet": "poi_recommendation",
    "nearby_parking": "poi_recommendation",
    "nearby_station": "poi_recommendation",
    "ticket_price": "strict_fact_lookup",
    "opening_hours": "strict_fact_lookup",
    "seasonal_operation_status": "strict_fact_lookup",
    "elevation": "geo_fact_lookup",
    "altitude": "geo_fact_lookup",
    "height_elevation": "geo_fact_lookup",
    "mountain_height": "geo_fact_lookup",
    "peak_height": "geo_fact_lookup",
    "highest_peak_elevation": "geo_fact_lookup",
    "main_peak_elevations": "geo_fact_lookup",
    "forecast": "live_status",
    "weather_today": "live_status",
    "weather": "live_status",
    "traffic_status": "live_status",
    "review_summary": "review_first",
    "value_for_money": "review_first",
}

MUST_ATTEMPT_COUNT: dict[str, int] = {
    "poi_recommendation": 2,
    "strict_fact_lookup": 2,
    "geo_fact_lookup": 1,
    "live_status": 1,
    "multi_place_parallel": 2,
    "route_first": 2,
    "review_first": 1,
    "mixed_advisory": 1,
    "minimal_probe": 1,
}

_IRRELEVANT_FOR_NEARBY = frozenset(
    {
        "wikipedia_mcp",
        "wikidata_mcp",
        "osm_mcp",
        "fallback",
        "knowledge_prior",
        "climate_mcp",
        "baidu_route_mcp",
        "baidu_route_matrix_mcp",
        "baidu_traffic_mcp",
        "baidu_reverse_geocode_mcp",
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
    }
)
_IRRELEVANT_FOR_LOOKUP = frozenset({"wikipedia_mcp", "wikidata_mcp", "fallback", "knowledge_prior"})

_GEO_RESOLUTION_CLAIMS = frozenset(
    {"entity_resolution", "geo_resolution", "place_lookup", "place_candidates"}
)


@dataclass
class ClaimRetrievalPlan:
    claim_type: str
    sequence_key: str
    tool_sequence: list[str] = field(default_factory=list)
    must_attempt: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)


@dataclass
class ToolSelection:
    tool_name: str
    claim_type: str
    tier: str
    reason: str
    tool_parameters_patch: dict = field(default_factory=dict)
    skip_preferred_override: bool = True


class S5DiversifiedToolSelector:
    def __init__(self, state: TravelAgentState) -> None:
        self.state = state
        self.ledger = get_ledger(state)
        self.strategy = resolve_intent_strategy(state.intent_profile)

    def _canonical_claim(self, claim_type: str) -> str:
        text = query_text_from_state(self.state)
        if is_nearby_need(claim_type):
            return resolve_nearby_need(claim_type, text=text)
        return normalize_need(claim_type)

    def primary_claim_type(self) -> str:
        contract = self.state.response_contract
        if contract:
            for req in contract.claim_requirements:
                if req.priority == "required":
                    return self._canonical_claim(req.claim_type)
            if contract.claim_requirements:
                return self._canonical_claim(contract.claim_requirements[0].claim_type)
        frame = self.state.semantic_frame
        if frame and frame.information_needs:
            return self._canonical_claim(frame.information_needs[0])
        need = ClaimSearchPlanner.primary_information_need(self.state)
        return self._canonical_claim(need or "general_travel_advice")

    def sequence_key_for_claim(self, claim_type: str) -> str:
        claim = self._canonical_claim(claim_type)
        if claim in CLAIM_SEQUENCE_OVERRIDE:
            return CLAIM_SEQUENCE_OVERRIDE[claim]
        if is_nearby_need(claim):
            return "poi_recommendation"
        if self.strategy:
            mode = self.strategy.retrieval_mode
            if mode in RETRIEVAL_TOOL_SEQUENCE:
                return mode
        return "mixed_advisory"

    def build_claim_plan(
        self,
        claim_type: str,
        *,
        whitelist: ToolWhitelist | None = None,
    ) -> ClaimRetrievalPlan:
        claim = self._canonical_claim(claim_type)
        seq_key = self.sequence_key_for_claim(claim)
        base = list(RETRIEVAL_TOOL_SEQUENCE.get(seq_key, RETRIEVAL_TOOL_SEQUENCE["mixed_advisory"]))

        extra: list[str] = []
        contract = self.state.response_contract
        if contract:
            for req in contract.claim_requirements:
                if self._canonical_claim(req.claim_type) == claim:
                    extra.extend(req.preferred_tools)
        if self.strategy:
            extra.extend(self.strategy.tool_tiers.primary)
            extra.extend(self.strategy.tool_tiers.secondary)

        if claim in _GEO_RESOLUTION_CLAIMS:
            merged = _dedupe_tools([*base, *extra])
        else:
            merged = _dedupe_tools([*extra, *base])
        merged = self._filter_sequence(merged, claim, whitelist)
        must_n = MUST_ATTEMPT_COUNT.get(seq_key, 1)
        must_attempt = merged[:must_n] if merged else []
        optional = merged[must_n:] if len(merged) > must_n else []
        return ClaimRetrievalPlan(
            claim_type=claim,
            sequence_key=seq_key,
            tool_sequence=merged,
            must_attempt=must_attempt,
            optional=optional,
        )

    def build_all_plans(self, whitelist: ToolWhitelist | None = None) -> dict[str, ClaimRetrievalPlan]:
        claims: list[str] = []
        contract = self.state.response_contract
        if contract:
            for req in contract.claim_requirements:
                c = self._canonical_claim(req.claim_type)
                if c not in claims:
                    claims.append(c)
        if not claims:
            claims = [self.primary_claim_type()]
        return {c: self.build_claim_plan(c, whitelist=whitelist) for c in claims}

    def select_next(
        self,
        claim_type: str,
        whitelist: ToolWhitelist | None,
        *,
        subagent: str | None = None,
        phase: Phase = "main",
        exclude_search_mcp_repeat: bool = True,
    ) -> ToolSelection | None:
        plan = self.build_claim_plan(claim_type, whitelist=whitelist)
        attempted = self.ledger.attempted_tools(claim_type=self._canonical_claim(claim_type))

        for tool in plan.tool_sequence:
            resolved = resolve_tool_name(tool)
            if whitelist is not None and not whitelist.is_allowed(resolved):
                continue
            if resolved in attempted:
                continue
            if exclude_search_mcp_repeat and resolved == "search_mcp":
                if self.ledger.attempt_count("search_mcp", claim_type=plan.claim_type) >= 2:
                    continue
            if not self.validate_tool_args(resolved, claim_type=plan.claim_type):
                self.ledger.record(
                    ToolAttemptRecord(
                        tool_name=resolved,
                        claim_type=plan.claim_type,
                        subagent=subagent,
                        phase=phase,
                        status="skipped_invalid_args",
                        evidence_count=0,
                    )
                )
                save_ledger(self.state, self.ledger)
                continue
            tier = "must_attempt" if resolved in {resolve_tool_name(t) for t in plan.must_attempt} else "optional"
            patch = self._tool_parameters_patch(resolved, plan.claim_type)
            return ToolSelection(
                tool_name=resolved,
                claim_type=plan.claim_type,
                tier=tier,
                reason=f"diversified:{plan.sequence_key}:{tier}",
                tool_parameters_patch=patch,
            )
        return None

    def must_attempt_remaining(self, whitelist: ToolWhitelist | None) -> list[str]:
        remaining: list[str] = []
        plans = self.build_all_plans(whitelist)
        attempted_global = self.ledger.attempted_tools()
        for plan in plans.values():
            for tool in plan.must_attempt:
                resolved = resolve_tool_name(tool)
                if resolved in attempted_global:
                    continue
                if whitelist is not None and not whitelist.is_allowed(resolved):
                    continue
                if not self.validate_tool_args(resolved, claim_type=plan.claim_type):
                    continue
                if resolved not in remaining:
                    remaining.append(resolved)
        return remaining

    def diversity_hints(self, whitelist: ToolWhitelist | None) -> list[str]:
        hints: list[str] = []
        plans = self.build_all_plans(whitelist)
        for claim, plan in plans.items():
            nxt = self.select_next(claim, whitelist)
            if nxt:
                hints.append(
                    f"{claim} ({plan.sequence_key}): next untried tool → {nxt.tool_name} ({nxt.tier})"
                )
            remaining = [
                t
                for t in plan.must_attempt
                if resolve_tool_name(t) not in self.ledger.attempted_tools()
            ]
            if remaining:
                hints.append(f"{claim}: must_attempt before FINISH: {', '.join(remaining)}")
        return hints

    def non_search_tool_queue(
        self,
        whitelist: ToolWhitelist | None,
        *,
        claim_type: str | None = None,
    ) -> list[str]:
        claim = self._canonical_claim(claim_type or self.primary_claim_type())
        plan = self.build_claim_plan(claim, whitelist=whitelist)
        queue: list[str] = []
        for tool in plan.tool_sequence:
            resolved = resolve_tool_name(tool)
            if resolved == "search_mcp":
                continue
            if whitelist is not None and not whitelist.is_allowed(resolved):
                continue
            if resolved in self.ledger.attempted_tools():
                continue
            if not self.validate_tool_args(resolved, claim_type=claim):
                continue
            queue.append(resolved)
        return queue

    def validate_tool_args(self, tool_name: str, *, claim_type: str | None = None) -> bool:
        tool = resolve_tool_name(tool_name)
        evidence = list(self.state.evidence or [])
        structured = self.state.structured_result
        claim = self._canonical_claim(claim_type or self.primary_claim_type())
        if is_nearby_need(claim) and tool in _IRRELEVANT_FOR_NEARBY:
            return False
        if tool == "baidu_place_search_mcp" and is_nearby_need(claim):
            if poi_anchor_satisfied(self.state):
                return (
                    resolve_coordinates_from_evidence(evidence, structured_result=structured) is not None
                )
            return True
        if tool == "baidu_place_detail_mcp":
            return bool(pick_baidu_uid_from_evidence(evidence))
        if tool == "baidu_route_mcp":
            goal = self.state.user_goal
            frame = self.state.semantic_frame
            if goal and goal.start_location and frame and frame.entities and frame.entities.places:
                return True
            return resolve_coordinates_from_evidence(evidence, structured_result=structured) is not None
        if tool == "baidu_route_matrix_mcp":
            frame = self.state.semantic_frame
            places = list(frame.entities.places or []) if frame and frame.entities else []
            return len(places) >= 2
        if tool in {"browser_mcp", "official_page_reader_mcp"}:
            return any(getattr(ev, "source_url", None) for ev in evidence) or ClaimSearchPlanner.search_call_count(
                self.state
            ) > 0
        return True

    def _tool_parameters_patch(self, tool_name: str, claim_type: str) -> dict:
        patch: dict[str, object] = {}
        frame = self.state.semantic_frame
        if tool_name == "baidu_place_search_mcp" and is_nearby_need(claim_type):
            if frame and frame.entities and frame.entities.places:
                patch.setdefault("query", f"{frame.entities.places[0]} 美食")
            coords = resolve_nearby_anchor_coordinates(
                list(self.state.evidence or []),
                user_query=self.state.raw_user_query or "",
                structured_result=self.state.structured_result,
            )
            patch.update(nearby_coordinate_patch(coords))
        return patch

    def _filter_sequence(
        self,
        tools: list[str],
        claim_type: str,
        whitelist: ToolWhitelist | None,
    ) -> list[str]:
        seq_key = self.sequence_key_for_claim(claim_type)
        irrelevant = _IRRELEVANT_FOR_NEARBY if seq_key == "poi_recommendation" else set()
        if seq_key == "strict_fact_lookup":
            irrelevant = _IRRELEVANT_FOR_LOOKUP
        out: list[str] = []
        for tool in tools:
            resolved = resolve_tool_name(tool)
            if resolved in irrelevant:
                continue
            if whitelist is not None and not whitelist.is_allowed(resolved):
                continue
            if resolved not in out:
                out.append(resolved)
        return out


def _dedupe_tools(tools: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tool in tools:
        resolved = resolve_tool_name(tool)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def store_retrieval_plans(state: TravelAgentState, whitelist: ToolWhitelist | None) -> dict[str, ClaimRetrievalPlan]:
    selector = S5DiversifiedToolSelector(state)
    plans = selector.build_all_plans(whitelist)
    structured = dict(state.structured_result or {})
    structured["s5_retrieval_plans"] = {
        k: {
            "claim_type": p.claim_type,
            "sequence_key": p.sequence_key,
            "tool_sequence": p.tool_sequence,
            "must_attempt": p.must_attempt,
            "optional": p.optional,
        }
        for k, p in plans.items()
    }
    state.structured_result = structured
    return plans


def select_tool_for_subagent(
    state: TravelAgentState,
    task: SearchTask,
    whitelist: ToolWhitelist | None,
    *,
    subagent: str,
    phase: Phase = "main",
) -> ToolSelection | None:
    selector = S5DiversifiedToolSelector(state)
    claim = selector._canonical_claim(task.claim_target or task.information_need or "")
    return selector.select_next(claim, whitelist, subagent=subagent, phase=phase)


def untried_must_attempt_tools(
    state: TravelAgentState,
    whitelist: ToolWhitelist | None,
) -> list[str]:
    return S5DiversifiedToolSelector(state).must_attempt_remaining(whitelist)


def diversity_hints_for_state(
    state: TravelAgentState,
    whitelist: ToolWhitelist | None,
) -> list[str]:
    return S5DiversifiedToolSelector(state).diversity_hints(whitelist)
