"""Compile SemanticFrame + context into a claim-level ResponseContract."""

from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.policies.evidence_policy import EvidencePolicy
from app.orchestrator.claim_policy_registry import enrich_claim_requirement
from app.orchestrator.information_need_aliases import (
    infer_all_nearby_needs_from_text,
    infer_nearby_need_from_text,
    is_nearby_need,
    nearby_claims_for_retrieval,
    normalize_information_needs,
    normalize_need,
    resolve_nearby_need,
)
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
from app.schemas.intent_profile import (
    AnswerStyle,
    EvidenceSensitivity,
    IntentProfile,
    PrimaryIntent,
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
_KEYWORD_NEED_HINTS: dict[str, str] = {
    "ticket_price": "门票",
    "opening_hours": "开放时间",
    "elevation": "海拔",
    "altitude": "海拔",
    "coordinates": "坐标",
    "general_information": "",
    "best_time_to_visit": "什么时候去",
    "seasonality": "最佳季节",
}

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

_NEARBY_PROVIDER_TOOLS = [
    "baidu_place_search_mcp",
    "baidu_place_detail_mcp",
    "dianping_nearby_crawler_mcp",
    "dianping_review_crawler_mcp",
    "ctrip_review_crawler_mcp",
    "search_mcp",
    "browser_mcp",
]

_PLACE_ENTITY_LABELS = frozenset(
    {
        "primary_subject",
        "place_mention",
        "ambiguous_place_candidate",
        "resolved_place",
        "alternate_name",
    }
)

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
        intent_profile: IntentProfile | None = None,
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
            normalized_needs = normalize_information_needs(list(frame.information_needs or []), text=text)
            for need in normalized_needs:
                claim = self._claim_for_need(need, frame)
                if claim and not any(c.claim_type == claim.claim_type for c in claims):
                    claims.append(claim)

            if frame.decision_type == DecisionType.BEST_TIME_TO_VISIT and not any(
                c.claim_type in {"best_time_to_visit", "seasonal_operation_status"} for c in claims
            ):
                claims.append(self._best_time_claim(frame))

        if not claims:
            if intent_profile and intent_profile.primary_intent == PrimaryIntent.NEARBY:
                fallback_needs = infer_all_nearby_needs_from_text(text)
                extras = list(dict.fromkeys(fallback_needs + ["review_summary"]))
                for extra in extras:
                    claim = self._claim_for_need(extra, frame)
                    if claim and not any(c.claim_type == claim.claim_type for c in claims):
                        claims.append(claim)
            elif frame.decision_type == DecisionType.NEARBY_SEARCH:
                for need in infer_all_nearby_needs_from_text(text):
                    claim = self._claim_for_need(need, frame)
                    if claim and not any(c.claim_type == claim.claim_type for c in claims):
                        claims.append(claim)
            if not claims:
                claims.append(self._general_advice_claim(frame))
        elif intent_profile and intent_profile.primary_intent == PrimaryIntent.NEARBY:
            if all(c.claim_type == "general_travel_advice" for c in claims):
                claims = []
                fallback_needs = infer_all_nearby_needs_from_text(text)
                extras = list(dict.fromkeys(fallback_needs + ["review_summary"]))
                for extra in extras:
                    claim = self._claim_for_need(extra, frame)
                    if claim:
                        claims.append(claim)
                if not claims:
                    claims.append(self._general_advice_claim(frame))

        claims = self._apply_intent_claim_hints(claims, intent_profile)
        if intent_profile and intent_profile.primary_intent == PrimaryIntent.COMPARISON:
            claims = self._ensure_comparison_claims(claims, frame)
        claims = self._append_provider_preferred_tools(claims)
        entity_policy = self._build_entity_policy(frame, text)
        gated_keywords = self._gate_search_keywords(frame, text, claims)
        clarification = self._build_clarification(frame, intent_profile)
        tool_strategy = self._build_tool_strategy(claims, settings.mcp_max_tool_calls_per_state, intent_profile)
        fallback = self._build_fallback_policy(claims, intent_profile)
        composition = self._build_composition_policy(frame, claims, intent_profile)
        risk = self._overall_risk(claims, entity_policy)

        if normalized:
            summary = normalized.rewritten_query or normalized.intent_summary or frame.raw_query
        else:
            summary = frame.normalized_request or frame.raw_query

        return ResponseContract(
            user_goal_summary=summary[:200],
            gated_search_keywords=gated_keywords,
            place_ambiguity_context=frame.place_ambiguity,
            entity_policy=entity_policy,
            claim_requirements=[enrich_claim_requirement(c) for c in claims],
            tool_strategy=tool_strategy,
            fallback_policy=fallback,
            clarification_policy=clarification,
            composition_policy=composition,
            overall_risk_level=risk,
            limitations_to_add=self._default_limitations(claims, frame),
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
            ticket_price_preferred = [
                "search_mcp",
                "official_source_discovery_mcp",
                "official_page_reader_mcp",
                "browser_mcp",
                "baidu_place_search_mcp",
                "baidu_place_detail_mcp",
                "baidu_geocode_mcp",
                "search_mcp",
                "official",
                *_TICKET_PRICE_PROVIDER_TOOLS,
            ]
            preferred = {
                "ticket_price": ticket_price_preferred,
                "opening_hours": [
                    "search_mcp",
                    "official_source_discovery_mcp",
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
                    "official_source_discovery_mcp",
                    "official_page_reader_mcp",
                    "browser_mcp",
                    "official",
                ],
                "reservation_policy": [
                    "search_mcp",
                    "official_source_discovery_mcp",
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
                    "ctrip_review_crawler_mcp",
                    "dianping_review_crawler_mcp",
                    "crowd_estimation_mcp",
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

        if need in {"transit", "transport_planning", "route_plan"}:
            claim_type = "route_plan" if need == "transit" else need
            return ClaimRequirement(
                claim_type=claim_type,
                priority="important",
                requires_exact_fact=False,
                requires_live_data=False,
                freshness="recent",
                allowed_source_types=["map", "transit_api", "public_web"],
                preferred_tools=[
                    "baidu_route_mcp",
                    "baidu_route_matrix_mcp",
                    "baidu_traffic_mcp",
                    "baidu_place_search_mcp",
                    "transit",
                    "search_mcp",
                ],
                forbidden_tools=["knowledge_prior"],
                model_prior_allowed=False,
                coverage_rule="route/transit context for comparison or access",
                missing_behavior="answer_with_limitation",
            )

        if need == "review_summary":
            return ClaimRequirement(
                claim_type="review_summary",
                priority="important",
                requires_exact_fact=False,
                allowed_source_types=["review", "public_web"],
                preferred_tools=[
                    "ctrip_review_crawler_mcp",
                    "dianping_review_crawler_mcp",
                    "search_mcp",
                    "reviews",
                ],
                forbidden_tools=["knowledge_prior"],
                model_prior_allowed=False,
                coverage_rule="review/experience signal for suitability comparison",
                missing_behavior="answer_with_limitation",
            )

        if need in _ADVISORY_NEEDS:
            return self._best_time_claim(frame, priority="important")

        if is_nearby_need(need):
            claim_type = resolve_nearby_need(need, text=f"{frame.raw_query} {frame.normalized_request}")
            return ClaimRequirement(
                claim_type=claim_type,
                claim_family="nearby_recommendation",
                priority="required",
                requires_exact_fact=False,
                requires_live_data=False,
                freshness="recent",
                allowed_source_types=["map", "review", "public_web"],
                preferred_tools=list(_NEARBY_PROVIDER_TOOLS),
                forbidden_tools=["knowledge_prior"],
                model_prior_allowed=False,
                estimation_allowed=False,
                coverage_rule="must list named POIs with distance or walk/drive time when available",
                missing_behavior="answer_with_limitation",
            )

        if need in {"elevation", "altitude", "area", "general_fact"}:
            claim_type = "elevation" if need == "altitude" else need
            return ClaimRequirement(
                claim_type=claim_type,
                priority="required" if frame.requires_exact_fact else "important",
                requires_exact_fact=bool(frame.requires_exact_fact),
                requires_live_data=False,
                freshness="stable",
                allowed_source_types=["public_web", "encyclopedia", "map", "official", "model_prior"],
                preferred_tools=[
                    "search_mcp",
                    "wikipedia_mcp",
                    "wikidata_mcp",
                    "osm_mcp",
                    "baidu_place_search_mcp",
                    "knowledge_prior",
                    "fallback",
                ],
                forbidden_tools=["knowledge_prior"] if frame.requires_exact_fact else [],
                model_prior_allowed=frame.can_answer_with_model_prior and not frame.requires_exact_fact,
                estimation_allowed=not frame.requires_exact_fact,
                coverage_rule=f"must cite explicit {need} value (e.g. meters) from web or encyclopedia",
                missing_behavior="answer_with_limitation",
            )

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
        hard = bool(frame.requires_exact_fact or frame.requires_live_data)
        return ClaimRequirement(
            claim_type="general_travel_advice",
            priority="required" if hard else "important",
            requires_exact_fact=hard,
            requires_live_data=bool(frame.requires_live_data),
            freshness="stable",
            allowed_source_types=["public_web", "official", "map", "model_prior"],
            preferred_tools=[
                "baidu_place_search_mcp",
                "baidu_place_detail_mcp",
                "baidu_geocode_mcp",
                "search_mcp",
                "wikipedia_mcp",
                "wikidata_mcp",
                "osm_mcp",
                "knowledge_prior",
                "fallback",
            ],
            forbidden_tools=["knowledge_prior"] if hard else [],
            model_prior_allowed=frame.can_answer_with_model_prior and not hard,
            estimation_allowed=not hard,
            missing_behavior="answer_with_limitation",
        )

    @staticmethod
    def _gate_search_keywords(
        frame: SemanticFrame,
        text: str,
        claims: list[ClaimRequirement],
    ) -> list[str]:
        """S3: gate S2 labeled entities/needs into retrieval keywords (preserve ambiguity)."""
        keywords: list[str] = []

        for ent in frame.labeled_entities or []:
            if not isinstance(ent, dict):
                continue
            labels = set(ent.get("labels") or [])
            if labels and not (labels & _PLACE_ENTITY_LABELS):
                continue
            name = str(ent.get("normalized_name") or ent.get("text") or "").strip()
            if name:
                keywords.append(name)
            if ent.get("region"):
                keywords.append(str(ent["region"]).strip())
            if ent.get("city"):
                keywords.append(str(ent["city"]).strip())

        ambiguity = frame.place_ambiguity
        if ambiguity and ambiguity.is_ambiguous:
            for candidate in ambiguity.candidates:
                if candidate.name:
                    keywords.append(candidate.name)
                if candidate.region:
                    keywords.append(candidate.region)
                if candidate.city:
                    keywords.append(candidate.city)

        entities = frame.entities
        if entities and not keywords:
            keywords.extend(entities.places or [])
            if entities.city:
                keywords.append(entities.city)
            if entities.region:
                keywords.append(entities.region)
            if entities.country and entities.country not in {"China", "中国"}:
                keywords.append(entities.country)

        for need in frame.information_needs:
            hint = _KEYWORD_NEED_HINTS.get(need)
            if hint:
                keywords.append(hint)
            elif need not in {"unknown", "general_information"}:
                keywords.append(need.replace("_", " "))

        if re.search(r"海拔|高度", text, re.I):
            keywords.append("海拔")

        for claim in claims:
            if claim.priority == "required" and claim.claim_type not in keywords:
                hint = _KEYWORD_NEED_HINTS.get(claim.claim_type)
                if hint:
                    keywords.append(hint)

        deduped: list[str] = []
        for token in keywords:
            token = str(token).strip()
            if len(token) < 2:
                continue
            if token not in deduped:
                deduped.append(token)
        return deduped[:12]

    @staticmethod
    def _has_required_hard_claims(claims: list[ClaimRequirement]) -> bool:
        return any(c.priority == "required" and not c.model_prior_allowed for c in claims)

    @staticmethod
    def _build_entity_policy(frame: SemanticFrame, text: str) -> EntityPolicy:
        """Geo tool hints; preserve ambiguity metadata for S5 without S3 clarification."""
        _ = text
        preferred: list[str] = []
        ambiguous = frame.place_ambiguity and frame.place_ambiguity.is_ambiguous
        reason = frame.place_ambiguity.reason if ambiguous else None

        if frame.entities and frame.entities.country in ("China", "中国", None, ""):
            if frame.entities.places and (ambiguous or not (frame.entities.city or frame.entities.region)):
                preferred = [
                    "baidu_place_search_mcp",
                    "baidu_geocode_mcp",
                    "baidu_place_detail_mcp",
                    "wikidata_mcp",
                    "osm_mcp",
                    "search_mcp",
                ]

        return EntityPolicy(
            requires_disambiguation=False,
            disambiguation_reason=reason,
            preferred_tools=preferred,
            if_multiple_candidates="answer_with_limitation",
            if_unresolved="answer_with_limitation",
        )

    _COMPARISON_CLAIM_TYPES = frozenset(
        {"crowd_level", "route_plan", "review_summary", "transit"}
    )

    @classmethod
    def _ensure_comparison_claims(
        cls,
        claims: list[ClaimRequirement],
        frame: SemanticFrame,
    ) -> list[ClaimRequirement]:
        compiler = ResponseContractCompiler()
        claims = [c for c in claims if c.claim_type in cls._COMPARISON_CLAIM_TYPES]
        existing = {c.claim_type for c in claims}
        for required in ("crowd_level", "route_plan", "review_summary"):
            if required in existing:
                continue
            if required == "crowd_level":
                claim = compiler._claim_for_need("crowd_level", frame)
            elif required == "route_plan":
                claim = compiler._claim_for_need("transit", frame) or compiler._claim_for_need(
                    "route_plan", frame
                )
            else:
                claim = compiler._claim_for_need("review_summary", frame)
            if claim and claim.claim_type not in existing:
                claims.append(claim)
                existing.add(claim.claim_type)
        return claims

    @staticmethod
    def _apply_intent_claim_hints(
        claims: list[ClaimRequirement],
        intent_profile: IntentProfile | None,
    ) -> list[ClaimRequirement]:
        if not intent_profile:
            return claims
        family_by_intent = {
            PrimaryIntent.LOOKUP: "hard_fact",
            PrimaryIntent.ADVISORY: "suitability_advice",
            PrimaryIntent.PLANNING: "route_context",
            PrimaryIntent.COMPARISON: "comparison",
            PrimaryIntent.REVIEW_CHECK: "review_signal",
            PrimaryIntent.REALTIME_CHECK: "live_status",
            PrimaryIntent.NEARBY: "nearby_recommendation",
            PrimaryIntent.CLARIFICATION: "clarification",
        }
        default_family = family_by_intent.get(intent_profile.primary_intent)
        if not default_family:
            return claims
        updated: list[ClaimRequirement] = []
        for claim in claims:
            if claim.claim_family:
                updated.append(claim)
                continue
            updated.append(claim.model_copy(update={"claim_family": default_family}))
        return updated

    @staticmethod
    def _build_clarification(
        frame: SemanticFrame,
        intent_profile: IntentProfile | None = None,
    ) -> ClarificationPolicy:
        if intent_profile and intent_profile.primary_intent == PrimaryIntent.CLARIFICATION:
            question = "您说的地点指哪一座城市/景区？请补充具体地名以便检索。"
            if frame.place_ambiguity and frame.place_ambiguity.candidates:
                names = [c.name for c in frame.place_ambiguity.candidates if c.name]
                if names:
                    question = f"「{frame.raw_query.strip()}」可能指：{'、'.join(names[:4])}，请问您指的是哪一个？"
            return ClarificationPolicy(
                should_ask=True,
                question=question,
                reason="IntentProfile 判定需澄清地点",
            )
        return ClarificationPolicy(should_ask=False)

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
    def _build_tool_strategy(
        claims: list[ClaimRequirement],
        max_steps: int,
        intent_profile: IntentProfile | None = None,
    ) -> ToolStrategy:
        initial: list[str] = []
        fallback: list[str] = ["fallback"]
        lookup_boost = [
            "official_source_discovery_mcp",
            "official_page_reader_mcp",
            "search_mcp",
        ]
        if intent_profile and intent_profile.primary_intent == PrimaryIntent.LOOKUP:
            for tool in lookup_boost:
                if tool not in initial:
                    initial.append(tool)
        effective_max = max_steps
        if intent_profile and intent_profile.primary_intent == PrimaryIntent.COMPARISON:
            effective_max = max(max_steps, get_settings().mcp_max_tool_calls_comparison)
        for claim in claims:
            if claim.priority in ("required", "important"):
                for tool in claim.preferred_tools:
                    if tool not in initial:
                        initial.append(tool)
        return ToolStrategy(
            initial_tools=initial,
            fallback_tools=fallback,
            max_tool_steps=effective_max,
        )

    @staticmethod
    def _build_fallback_policy(
        claims: list[ClaimRequirement],
        intent_profile: IntentProfile | None = None,
    ) -> FallbackPolicy:
        allow_prior = any(c.model_prior_allowed for c in claims)
        has_hard_required = any(
            c.priority == "required" and not c.model_prior_allowed for c in claims
        )
        if intent_profile:
            if intent_profile.evidence_sensitivity == EvidenceSensitivity.MODEL_PRIOR_ALLOWED:
                allow_prior = allow_prior and not has_hard_required
            elif intent_profile.evidence_sensitivity in {
                EvidenceSensitivity.HARD_FACT,
                EvidenceSensitivity.LIVE_REQUIRED,
            }:
                allow_prior = False
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
        intent_profile: IntentProfile | None = None,
    ) -> CompositionPolicy:
        has_hard = any(c.priority == "required" and not c.model_prior_allowed for c in claims)
        style = "advisory"
        if intent_profile:
            style_map = {
                AnswerStyle.DIRECT_FACT: "direct",
                AnswerStyle.ADVISORY: "advisory",
                AnswerStyle.ITINERARY: "itinerary",
                AnswerStyle.COMPARISON: "comparison",
                AnswerStyle.RECOMMENDATION_LIST: "advisory",
                AnswerStyle.CLARIFICATION: "clarification",
            }
            style = style_map.get(intent_profile.answer_style, "advisory")
        elif frame.decision_type == DecisionType.FACT_LOOKUP or has_hard:
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
        return "low"

    @staticmethod
    def _default_limitations(claims: list[ClaimRequirement], frame: SemanticFrame | None = None) -> list[str]:
        limits: list[str] = []
        if frame and frame.place_ambiguity and frame.place_ambiguity.is_ambiguous:
            names = [c.name for c in frame.place_ambiguity.candidates if c.name]
            if names:
                limits.append(
                    "用户提及的地名可能存在多地同名："
                    + "、".join(names[:4])
                    + "；回答将基于检索证据消歧，而非提前假定唯一地点。"
                )
            elif frame.place_ambiguity.reason:
                limits.append(frame.place_ambiguity.reason)
        if any(c.claim_type == "best_time_to_visit" for c in claims):
            limits.append(
                "季节建议基于公开资料或一般规律；具体年份天气与节庆日期需进一步核实。"
            )
        if any(c.claim_type == "seasonal_operation_status" for c in claims):
            limits.append("开放/通车月份以当年官方公告为准，实施前请核对最新通知。")
        return limits
