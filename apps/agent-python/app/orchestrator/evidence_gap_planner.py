"""Plan EvidenceGapRequest when S7 finds insufficient coverage."""

from __future__ import annotations

from app.orchestrator.claim_policy_registry import ClaimPolicyView
from app.schemas.evidence_decision_report import ClaimDecision
from app.schemas.evidence_gap_request import EvidenceGapRequest
from app.schemas.response_contract import ClaimRequirement
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name
from app.tools.mcp.tool_specs import NEED_TOOL_PROFILES


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
        "{city} {place_name} 门票",
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
        if decision.coverage_quality in {"strong", "partial"} and decision.adoption in {
            "adopt",
            "adopt_with_limitation",
        }:
            return None
        if decision.adoption == "omit" and claim.priority == "optional":
            return None
        if claim.priority not in {"required", "important"} and decision.coverage_quality != "none":
            return None

        tried = self._tried_tools(state)
        failed = self._failed_tools(state)
        untried = [t for t in policy.preferred_tools if resolve_tool_name(t) not in tried]
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
            return None

        place = self._place_name(state)
        city = self._city(state)
        templates = _GAP_TEMPLATES.get(
            claim.claim_type,
            [
                f"{{place_name}} {claim.claim_description or claim.claim_type}",
                f"{{city}} {{place_name}} {claim.claim_type.replace('_', ' ')}",
            ],
        )
        rendered = [
            t.format(place_name=place, city=city, claim_type=claim.claim_type, user_query=state.raw_user_query)
            for t in templates
        ]

        suggested_tools = untried[:4] or ["search_mcp"]
        gap = EvidenceGapRequest(
            claim_type=claim.claim_type,
            claim_family=policy.claim_family,
            claim_description=policy.claim_description,
            reason=decision.reason or f"missing evidence for {claim.claim_type}",
            missing_evidence_need=claim.claim_type,
            suggested_domains=self._domains_for_family(policy.claim_family),
            suggested_tools=suggested_tools,
            query_templates=rendered,
            forbidden_tools=list(policy.forbidden_tools),
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
        frame = state.semantic_frame
        if frame and frame.entities.places:
            return frame.entities.places[0]
        return "目的地"

    @staticmethod
    def _city(state: TravelAgentState) -> str:
        frame = state.semantic_frame
        if frame and frame.entities.city:
            return frame.entities.city
        return ""

    @staticmethod
    def _domains_for_family(family: str) -> list[str]:
        return {
            "ticket_booking": ["ticket_platform_provider", "search_provider"],
            "review_experience": ["crawler_provider", "search_provider"],
            "suitability_advice": ["crawler_provider", "search_provider"],
            "hard_fact": ["official_web_provider", "search_provider"],
            "operation_status": ["official_web_provider", "search_provider"],
        }.get(family, ["search_provider"])
