"""Compile SemanticFrame + context into a claim-level ResponseContract."""

from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.normalized_user_request import NormalizedUserRequest
from app.schemas.response_contract import (
    ClaimRequirement,
    ClarificationPolicy,
    CompositionPolicy,
    EntityPolicy,
    FallbackPolicy,
    ResponseContract,
    ToolStrategy,
)
from app.schemas.semantic_frame import DecisionType, SemanticFrame


_OPENING_PERIOD_PATTERNS = re.compile(
    r"开放|通车|开放月份|几月份开放|什么时候开放|何时开放|开放时间|营业季|封路",
    re.I,
)
_ROAD_OR_SCENIC_HINTS = re.compile(
    r"公路|高速|国道|省道|景区|国家公园|森林公园|大峡谷|独库|天山|公路",
    re.I,
)
_AMBIGUOUS_PLACE_HINTS = re.compile(
    r"山|峰|湖|河|谷|公路|高速|景区|公园|古镇|古城",
    re.I,
)
_ADMIN_REGION_HINTS = re.compile(
    r"新疆|西藏|内蒙古|广西|宁夏|香港|澳门|台湾"
    r"|黑龙江|吉林|辽宁|河北|山西|陕西|甘肃|青海|山东|河南|江苏|浙江|安徽|福建|江西|湖北|湖南|广东|海南|四川|贵州|云南"
    r"|北京|上海|天津|重庆"
    r"|[^，,、\s]{2,8}(?:省|自治区|特别行政区|维吾尔|壮族|回族)",
    re.I,
)

_HARD_FACT_NEEDS = frozenset(
    {
        "ticket_price",
        "opening_hours",
        "temporary_closure",
        "reservation_policy",
    }
)

_WEATHER_NEEDS = frozenset({"today_weather", "forecast", "weather", "weather_today"})

_CROWD_NEEDS = frozenset({"current_crowd", "queue_time", "crowd_level"})

_ADVISORY_NEEDS = frozenset({"best_time_to_visit", "seasonality"})

_TICKET_PRICE_PROVIDER_TOOLS = [
    "ticketlens_experience_mcp",
    "fliggy_ticket_snapshot_crawler_mcp",
    "ctrip_ticket_signal_crawler_mcp",
    "dianping_ticket_signal_crawler_mcp",
    "ticket_price_history_query",
]

_REVIEW_PROVIDER_TOOLS = [
    "ctrip_review_crawler_mcp",
    "dianping_review_crawler_mcp",
    "fliggy_ticket_review_signal_mcp",
    "ticketlens_experience_mcp",
    "ticketlens_experience_review_signal_mcp",
]

_REVIEW_CLAIM_TYPES = frozenset(
    {
        "review_summary",
        "value_for_money",
        "elderly_suitability",
        "family_friendly",
        "commercialization_risk",
        "crowd_risk",
        "queue_risk",
    }
)


class ResponseContractCompiler:
    """SemanticFrame → ResponseContract (claim-level evidence plan)."""

    def compile(
        self,
        frame: SemanticFrame,
        normalized: NormalizedUserRequest | None = None,
        *,
        conversation_context: dict[str, Any] | None = None,
        available_tools: set[str] | None = None,
    ) -> ResponseContract:
        _ = conversation_context
        _ = available_tools
        settings = get_settings()
        norm_text = ""
        if normalized:
            norm_text = normalized.rewritten_query or normalized.intent_summary or ""
        text = f"{frame.raw_query} {frame.normalized_request} {norm_text}".strip()
        claims: list[ClaimRequirement] = []

        if self._detect_seasonal_operation_status(frame, text):
            claims.append(self._seasonal_operation_status_claim())
            claims.append(self._general_seasonal_context_claim())
        else:
            for need in frame.information_needs:
                claim = self._claim_for_need(need, frame)
                if claim and not any(c.claim_type == claim.claim_type for c in claims):
                    claims.append(claim)

            if frame.decision_type == DecisionType.BEST_TIME_TO_VISIT and not any(
                c.claim_type in {"best_time_to_visit", "seasonal_operation_status"} for c in claims
            ):
                claims.append(self._best_time_claim(frame))

        if not claims:
            claims.append(self._general_advice_claim(frame))

        claims = self._append_provider_preferred_tools(claims)
        entity_policy = self._build_entity_policy(frame, text)
        clarification = self._build_clarification(frame, entity_policy, claims)
        tool_strategy = self._build_tool_strategy(claims, settings.mcp_max_tool_calls_per_state)
        fallback = self._build_fallback_policy(claims)
        composition = self._build_composition_policy(frame, claims)
        risk = self._overall_risk(claims, entity_policy)

        if normalized:
            summary = normalized.rewritten_query or normalized.intent_summary or frame.raw_query
        else:
            summary = frame.normalized_request or frame.raw_query

        return ResponseContract(
            user_goal_summary=summary[:200],
            entity_policy=entity_policy,
            claim_requirements=claims,
            tool_strategy=tool_strategy,
            fallback_policy=fallback,
            clarification_policy=clarification,
            composition_policy=composition,
            overall_risk_level=risk,
            limitations_to_add=self._default_limitations(claims),
        )

    @staticmethod
    def _detect_seasonal_operation_status(frame: SemanticFrame, text: str) -> bool:
        if not _OPENING_PERIOD_PATTERNS.search(text):
            return False
        if _ROAD_OR_SCENIC_HINTS.search(text):
            return True
        if frame.entities.places and any(
            _ROAD_OR_SCENIC_HINTS.search(p) for p in frame.entities.places
        ):
            return True
        return "road" in text.lower() or "highway" in text.lower()

    @staticmethod
    def _seasonal_operation_status_claim() -> ClaimRequirement:
        return ClaimRequirement(
            claim_type="seasonal_operation_status",
            priority="required",
            requires_exact_fact=True,
            requires_live_data=False,
            freshness="recent",
            allowed_source_types=["official", "public_web", "tourism_board", "map"],
            preferred_tools=[
                "search_mcp",
                "official_page_reader_mcp",
                "browser_mcp",
                "baidu_place_search_mcp",
                "baidu_place_detail_mcp",
                "baidu_geocode_mcp",
            ],
            forbidden_tools=["knowledge_prior"],
            model_prior_allowed=False,
            estimation_allowed=False,
            coverage_rule="must cite recent official/public evidence for seasonal opening period",
            missing_behavior="answer_with_limitation",
        )

    @staticmethod
    def _general_seasonal_context_claim() -> ClaimRequirement:
        return ClaimRequirement(
            claim_type="general_seasonal_context",
            priority="optional",
            requires_exact_fact=False,
            freshness="seasonal",
            allowed_source_types=["model_prior", "public_web", "climate_api"],
            preferred_tools=["knowledge_prior", "search_mcp", "seasonality"],
            model_prior_allowed=True,
            estimation_allowed=True,
            coverage_rule="general seasonal background only; cannot substitute official opening period",
            missing_behavior="omit_claim",
        )

    def _claim_for_need(self, need: str, frame: SemanticFrame) -> ClaimRequirement | None:
        policy = EvidencePolicy.get(need)

        if need in _HARD_FACT_NEEDS:
            city_known = bool((frame.entities.city or "").strip()) if frame.entities else False
            ticket_price_preferred = (
                [
                    *_TICKET_PRICE_PROVIDER_TOOLS,
                    "official_page_reader_mcp",
                    "browser_mcp",
                    "search_mcp",
                    "official",
                    "baidu_place_search_mcp",
                    "baidu_place_detail_mcp",
                ]
                if city_known
                else [
                    "baidu_place_search_mcp",
                    "baidu_place_detail_mcp",
                    "baidu_geocode_mcp",
                    "search_mcp",
                    "official_page_reader_mcp",
                    "browser_mcp",
                    "official",
                ]
            )
            preferred = {
                "ticket_price": ticket_price_preferred,
                "opening_hours": [
                    "baidu_place_search_mcp",
                    "baidu_place_detail_mcp",
                    "baidu_geocode_mcp",
                    "official_page_reader_mcp",
                    "browser_mcp",
                    "search_mcp",
                    "official",
                ],
                "temporary_closure": [
                    "search_mcp",
                    "official_page_reader_mcp",
                    "browser_mcp",
                    "official",
                ],
                "reservation_policy": [
                    "official_page_reader_mcp",
                    "browser_mcp",
                    "search_mcp",
                    "official",
                ],
            }.get(need, ["search_mcp", "official_page_reader_mcp"])
            return ClaimRequirement(
                claim_type=need,
                priority="required",
                requires_exact_fact=True,
                requires_live_data=policy.requires_live_data,
                freshness="today" if need == "opening_hours" else "recent",
                allowed_source_types=["official", "public_web", "map", "tourism_board"],
                preferred_tools=preferred,
                forbidden_tools=["knowledge_prior"],
                model_prior_allowed=False,
                coverage_rule=f"must have explicit claim for the requested hard fact: {need}",
                missing_behavior="answer_with_limitation",
            )

        if need in _WEATHER_NEEDS:
            return ClaimRequirement(
                claim_type=need if need != "weather_today" else "weather_today",
                priority="required",
                requires_live_data=True,
                freshness="today",
                allowed_source_types=["weather_api", "map"],
                preferred_tools=[
                    "baidu_geocode_mcp",
                    "baidu_weather_mcp",
                    "openmeteo_mcp",
                    "weather_mcp",
                    "weather",
                ],
                forbidden_tools=["knowledge_prior"],
                model_prior_allowed=False,
                coverage_rule="must have live weather evidence",
                missing_behavior="answer_with_limitation",
            )

        if need in _CROWD_NEEDS:
            return ClaimRequirement(
                claim_type=need,
                priority="important",
                requires_live_data=True,
                freshness="real_time",
                allowed_source_types=["review", "map_proxy", "public_web"],
                preferred_tools=[
                    "search_mcp",
                    "baidu_place_detail_mcp",
                    "places_mcp",
                    "reviews",
                    "fallback",
                ],
                forbidden_tools=["knowledge_prior"],
                model_prior_allowed=False,
                estimation_allowed=True,
                coverage_rule="crowd proxy or live estimate with limitation",
                missing_behavior="answer_with_limitation",
            )

        if need in _ADVISORY_NEEDS:
            return self._best_time_claim(frame, priority="important")

        return None

    @staticmethod
    def _best_time_claim(
        frame: SemanticFrame,
        *,
        priority: str = "important",
    ) -> ClaimRequirement:
        return ClaimRequirement(
            claim_type="best_time_to_visit",
            priority=priority,  # type: ignore[arg-type]
            requires_exact_fact=False,
            requires_live_data=False,
            freshness="seasonal",
            allowed_source_types=["public_web", "tourism_board", "weather_api", "map", "model_prior"],
            preferred_tools=[
                "baidu_place_search_mcp",
                "baidu_place_detail_mcp",
                "baidu_geocode_mcp",
                "search_mcp",
                "climate_mcp",
                "openmeteo_mcp",
                "seasonality",
                "knowledge_prior",
            ],
            model_prior_allowed=frame.can_answer_with_model_prior,
            estimation_allowed=True,
            coverage_rule="should contain destination-specific month/season advice or explain uncertainty",
            missing_behavior="answer_with_limitation",
        )

    @staticmethod
    def _general_advice_claim(frame: SemanticFrame) -> ClaimRequirement:
        return ClaimRequirement(
            claim_type="general_travel_advice",
            priority="important",
            freshness="stable",
            allowed_source_types=["public_web", "model_prior"],
            preferred_tools=["search_mcp", "wikipedia_mcp", "knowledge_prior", "fallback"],
            model_prior_allowed=frame.can_answer_with_model_prior,
            estimation_allowed=True,
            missing_behavior="answer_with_limitation",
        )

    @staticmethod
    def _has_location_anchor(frame: SemanticFrame, text: str) -> bool:
        city = (frame.entities.city or "").strip()
        region = (frame.entities.region or "").strip()
        if city or region:
            return True
        return bool(_ADMIN_REGION_HINTS.search(text))

    @staticmethod
    def _has_required_hard_claims(claims: list[ClaimRequirement]) -> bool:
        return any(c.priority == "required" and not c.model_prior_allowed for c in claims)

    @staticmethod
    def _build_entity_policy(frame: SemanticFrame, text: str) -> EntityPolicy:
        country = (frame.entities.country or "").lower()
        places = frame.entities.places or []
        needs_disambiguation = False
        reason: str | None = None

        if (
            country in ("china", "中国")
            and places
            and not ResponseContractCompiler._has_location_anchor(frame, text)
        ):
            place_blob = " ".join(places) + text
            if _AMBIGUOUS_PLACE_HINTS.search(place_blob):
                needs_disambiguation = True
                reason = "国内地点缺少省/市/行政区，可能存在同名地点"

        preferred = []
        if needs_disambiguation:
            preferred = [
                "baidu_place_search_mcp",
                "baidu_geocode_mcp",
                "baidu_reverse_geocode_mcp",
                "wikidata_mcp",
                "osm_mcp",
                "search_mcp",
            ]

        return EntityPolicy(
            requires_disambiguation=needs_disambiguation,
            disambiguation_reason=reason,
            preferred_tools=preferred,
            if_multiple_candidates="ask_clarification",
            if_unresolved="answer_with_limitation",
        )

    @staticmethod
    def _build_clarification(
        frame: SemanticFrame,
        entity_policy: EntityPolicy,
        claims: list[ClaimRequirement],
    ) -> ClarificationPolicy:
        if frame.needs_clarification or "place_reference" in frame.missing_slots:
            return ClarificationPolicy(
                should_ask=True,
                question="请补充具体地点或城市，以便继续查询。",
                reason="关键地点信息缺失",
            )
        if entity_policy.requires_disambiguation:
            if ResponseContractCompiler._has_required_hard_claims(claims):
                return ClarificationPolicy(
                    should_ask=False,
                    reason="存在 required 强事实 claim，优先工具消歧",
                )
            place = frame.entities.places[0] if frame.entities.places else "该地点"
            return ClarificationPolicy(
                should_ask=True,
                question=f"{place} 在多地有同名地点，您指的是哪个省市？",
                reason=entity_policy.disambiguation_reason,
            )
        return ClarificationPolicy()

    @staticmethod
    def _append_provider_preferred_tools(claims: list[ClaimRequirement]) -> list[ClaimRequirement]:
        updated: list[ClaimRequirement] = []
        for claim in claims:
            extra: list[str] = []
            if claim.claim_type == "ticket_price":
                extra = _TICKET_PRICE_PROVIDER_TOOLS
            elif claim.claim_type in _REVIEW_CLAIM_TYPES:
                extra = _REVIEW_PROVIDER_TOOLS
            if not extra:
                updated.append(claim)
                continue
            # Providers already inlined for ticket_price when city anchor exists.
            missing = [t for t in extra if t not in claim.preferred_tools]
            if not missing:
                updated.append(claim)
                continue
            merged = list(dict.fromkeys([*claim.preferred_tools, *missing]))
            updated.append(claim.model_copy(update={"preferred_tools": merged}))
        return updated

    @staticmethod
    def _build_tool_strategy(claims: list[ClaimRequirement], max_steps: int) -> ToolStrategy:
        initial: list[str] = []
        fallback: list[str] = ["fallback"]
        for claim in claims:
            if claim.priority in ("required", "important"):
                for tool in claim.preferred_tools:
                    if tool not in initial:
                        initial.append(tool)
        return ToolStrategy(
            initial_tools=initial,
            fallback_tools=fallback,
            max_tool_steps=max_steps,
        )

    @staticmethod
    def _build_fallback_policy(claims: list[ClaimRequirement]) -> FallbackPolicy:
        allow_prior = any(c.model_prior_allowed for c in claims)
        allow_partial = not all(
            c.priority == "required" and c.requires_exact_fact for c in claims
        )
        return FallbackPolicy(
            allow_model_prior_fallback=allow_prior,
            allow_partial_answer=allow_partial,
            no_evidence_behavior="answer_with_limitation",
        )

    @staticmethod
    def _build_composition_policy(
        frame: SemanticFrame,
        claims: list[ClaimRequirement],
    ) -> CompositionPolicy:
        has_hard = any(c.priority == "required" and not c.model_prior_allowed for c in claims)
        style = "advisory"
        if frame.decision_type == DecisionType.FACT_LOOKUP or has_hard:
            style = "direct"
        if any(c.claim_type == "seasonal_operation_status" for c in claims):
            style = "direct"
        return CompositionPolicy(
            must_cite_evidence=has_hard,
            distinguish_fact_vs_prior=True,
            include_tool_failures_when_relevant=True,
            forbid_unsupported_claims=True,
            answer_style=style,  # type: ignore[arg-type]
        )

    @staticmethod
    def _overall_risk(
        claims: list[ClaimRequirement],
        entity_policy: EntityPolicy,
    ) -> str:
        if any(c.priority == "required" and c.requires_exact_fact for c in claims):
            return "high"
        if entity_policy.requires_disambiguation:
            return "medium"
        return "low"

    @staticmethod
    def _default_limitations(claims: list[ClaimRequirement]) -> list[str]:
        limits: list[str] = []
        if any(c.claim_type == "best_time_to_visit" for c in claims):
            limits.append(
                "季节建议基于公开资料或一般规律；具体年份天气与节庆日期需进一步核实。"
            )
        if any(c.claim_type == "seasonal_operation_status" for c in claims):
            limits.append("开放/通车月份以当年官方公告为准，实施前请核对最新通知。")
        return limits
