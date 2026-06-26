"""Plan EvidenceGapRequest when S7 finds insufficient coverage."""

from __future__ import annotations

from app.orchestrator.claim_policy_registry import ClaimPolicyView
from app.config import get_settings
from app.orchestrator.comparison_helpers import active_place_name, is_comparison_mode
from app.orchestrator.information_need_aliases import is_nearby_need
from app.orchestrator.official_source_judgement import needs_official_source_gap
from app.schemas.evidence_decision_report import ClaimDecision
from app.schemas.evidence_gap_request import EvidenceGapRequest
from app.schemas.response_contract import ClaimRequirement
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name
from app.tools.mcp.tool_specs import NEED_TOOL_PROFILES


_GAP_IRRELEVANT_ROUTE_TOOLS = frozenset(
    {"baidu_route_mcp", "baidu_route_matrix_mcp", "baidu_traffic_mcp", "baidu_reverse_geocode_mcp"}
)

_GAP_TEMPLATES: dict[str, list[str]] = {
    "photo_costume_suitability": [
        "{place_name} 汉服 拍照 游客评价",
        "{place_name} 古风 拍照 出片",
        "{place_name} 穿汉服 方便吗",
    ],
    "pet_friendly_suitability": [
        "{place_name} 可以带狗吗",
        "{place_name} 宠物 规定",
        "{place_name} 游客 带狗 评价",
    ],
    "commercialization_risk": [
        "{place_name} 商业化严重吗 游客评价",
        "{place_name} 值不值得去",
        "{place_name} 避坑 评价",
    ],
    "ticket_price": [
        "{place_name} 门票价格",
        "{place_name} 官方 票价",
        "{place_name} 官网 门票",
        "{city} {place_name} 门票",
    ],
    "opening_hours": [
        "{place_name} 官网 开放时间",
        "{place_name} 营业时间",
        "{city} {place_name} 开放时间",
    ],
    "seasonal_operation_status": [
        "{place_name} 官方 开放 公告",
        "{place_name} 闭园 通知",
        "{city} {place_name} 季节性 开放",
    ],
    "crowd_level": [
        "{region} {city} {place_name} 旅游旺季 拥挤程度",
        "{place_name} 游客多吗 评价",
        "{city} {place_name} crowd level",
    ],
    "route_plan": [
        "{place_name} 交通 怎么去",
        "{city} {place_name} 自驾 公共交通",
        "{place_name} 到 {peer_place} 交通",
    ],
    "transit": [
        "{place_name} 交通 怎么去",
        "{city} {place_name} 自驾",
    ],
    "review_summary": [
        "{place_name} 游客评价 值不值得去",
        "{city} {place_name} 攻略 评价",
        "{place_name} 避坑",
    ],
}


class EvidenceGapPlanner:
    def plan_gaps(
        self,
        state: TravelAgentState,
        claim: ClaimRequirement,
        policy: ClaimPolicyView,
        decision: ClaimDecision,
        *,
        gap_round: int,
        max_gap_rounds: int,
    ) -> EvidenceGapRequest | None:
        if gap_round >= max_gap_rounds:
            return None
        if decision.adoption == "omit" and claim.priority == "optional":
            return None
        if not needs_official_source_gap(state.evidence, claim.claim_type, decision):
            if decision.coverage_quality in {"strong", "partial"} and decision.adoption in {
                "adopt",
                "adopt_with_limitation",
            }:
                return None
        if claim.priority not in {"required", "important"} and decision.coverage_quality != "none":
            if not needs_official_source_gap(state.evidence, claim.claim_type, decision):
                return None

        tried = self._tried_tools(state)
        failed = self._failed_tools(state)
        untried = [t for t in policy.preferred_tools if resolve_tool_name(t) not in tried]
        if is_nearby_need(claim.claim_type):
            untried = [
                t
                for t in untried
                if resolve_tool_name(t) not in _GAP_IRRELEVANT_ROUTE_TOOLS
            ]
        profile = NEED_TOOL_PROFILES.get(claim.claim_type, [])

        def _tool_rank(tool: str) -> int:
            resolved = resolve_tool_name(tool)
            try:
                return profile.index(resolved)
            except ValueError:
                return 999

        untried = sorted(untried, key=_tool_rank)
        if not untried and decision.coverage_quality not in {"none", "weak"}:
            return None
        if decision.coverage_quality == "none" and not untried:
            if is_comparison_mode(state):
                untried = [
                    t
                    for t in [
                        "search_mcp",
                        "ctrip_review_crawler_mcp",
                        "dianping_review_crawler_mcp",
                        "baidu_route_mcp",
                        "baidu_route_matrix_mcp",
                    ]
                    if resolve_tool_name(t) not in tried
                ]
            if not untried:
                return None

        place = self._place_name(state)
        city = self._city(state)
        region = self._region(state)
        peer = self._peer_place(state, place)

        from app.orchestrator.claim_search_planner import ClaimSearchPlanner
        from app.orchestrator.search_query_rewriter import SearchQueryRewriter

        planner_ctx = ClaimSearchPlanner.planning_context(state)
        rewriter = SearchQueryRewriter.from_planning_context(planner_ctx, state)
        if claim.claim_type in _GAP_TEMPLATES:
            templates = _GAP_TEMPLATES[claim.claim_type]
            rendered = [
                t.format(
                    place_name=place,
                    city=city,
                    region=region,
                    claim_type=claim.claim_type,
                    user_query=state.raw_user_query,
                    peer_place=peer,
                )
                for t in templates
            ]
        else:
            rendered = rewriter.gap_query_templates(claim.claim_type, max_queries=4)

        suggested_tools = untried[:4] or ["search_mcp"]
        if needs_official_source_gap(state.evidence, claim.claim_type, decision):
            if "official_source_discovery_mcp" not in suggested_tools:
                suggested_tools = ["official_source_discovery_mcp", *suggested_tools][:4]
            reason = (
                decision.reason
                or f"missing official source support for {claim.claim_type}"
            )
        else:
            reason = decision.reason or f"missing evidence for {claim.claim_type}"
        forbidden = list(dict.fromkeys([*(policy.forbidden_tools or []), "knowledge_prior"]))
        if is_comparison_mode(state) and "search_mcp" not in suggested_tools:
            suggested_tools = ["search_mcp", *suggested_tools][:4]
        gap = EvidenceGapRequest(
            claim_type=claim.claim_type,
            claim_family=policy.claim_family,
            claim_description=policy.claim_description,
            reason=reason,
            missing_evidence_need=claim.claim_type,
            suggested_domains=self._domains_for_claim(claim.claim_type, policy.claim_family),
            suggested_tools=suggested_tools,
            query_templates=rendered,
            forbidden_tools=forbidden,
            already_tried_tools=tried,
            failed_tools=failed,
            max_extra_steps=3,
            priority="high" if claim.priority == "required" else "medium",
        )
        gap.ensure_signature()
        return gap

    @staticmethod
    def _tried_tools(state: TravelAgentState) -> list[str]:
        return list(dict.fromkeys(resolve_tool_name(t.tool_name) for t in state.tool_traces))

    @staticmethod
    def _failed_tools(state: TravelAgentState) -> list[str]:
        return list(
            dict.fromkeys(
                resolve_tool_name(t.tool_name) for t in state.tool_traces if t.status != "ok"
            )
        )

    @staticmethod
    def _place_name(state: TravelAgentState) -> str:
        active = active_place_name(state)
        if active:
            return active
        frame = state.semantic_frame
        if frame and frame.entities.places:
            return frame.entities.places[0]
        return "目的地"

    @staticmethod
    def _peer_place(state: TravelAgentState, place: str) -> str:
        peers = list(state.comparison_peer_places or [])
        for peer in peers:
            if peer and peer != place:
                return peer
        frame = state.semantic_frame
        if frame and frame.entities.places:
            for peer in frame.entities.places:
                if peer and peer != place:
                    return peer
        return ""

    @staticmethod
    def _region(state: TravelAgentState) -> str:
        frame = state.semantic_frame
        if frame and frame.entities.region:
            return frame.entities.region
        return ""

    @staticmethod
    def _city(state: TravelAgentState) -> str:
        frame = state.semantic_frame
        if frame and frame.entities.city:
            return frame.entities.city
        return ""

    @staticmethod
    def _domains_for_claim(claim_type: str, family: str) -> list[str]:
        by_claim = {
            "ticket_price": ["official_web_provider", "ticket_booking", "search_provider"],
            "opening_hours": ["official_web_provider", "search_provider"],
            "seasonal_operation_status": ["official_web_provider", "operation_status", "search_provider"],
            "road_opening_period": ["official_web_provider", "operation_status", "search_provider"],
            "temporary_closure": ["official_web_provider", "operation_status", "search_provider"],
            "reservation_policy": ["official_web_provider", "ticket_booking", "search_provider"],
        }
        if claim_type in by_claim:
            return by_claim[claim_type]
        return EvidenceGapPlanner._domains_for_family(family)

    @staticmethod
    def _domains_for_family(family: str) -> list[str]:
        return {
            "ticket_booking": ["ticket_platform_provider", "search_provider"],
            "review_experience": ["crawler_provider", "search_provider"],
            "suitability_advice": ["crawler_provider", "search_provider"],
            "hard_fact": ["official_web_provider", "search_provider"],
            "operation_status": ["official_web_provider", "search_provider"],
        }.get(family, ["search_provider"])
