import json
import logging
import re
from pathlib import Path

from app.orchestrator.claim_search_planner import is_search_miss_value
from app.orchestrator.comparison_helpers import (
    places_match,
    summarize_comparison_claims_for_compose,
)
from app.orchestrator.trace import TraceRecorder
from app.policies.citation_policy import CitationPolicy
from app.schemas.evidence import Evidence
from app.schemas.evidence_brief import EvidenceBrief
from app.schemas.final_answer_draft import FinalAnswerDraft, FinalAnswerSection
from app.schemas.intent_profile import AnswerStyle
from app.schemas.user_need_residual import UserNeedResidual
from app.schemas.user_query import TravelAgentState
from app.utils.llm_json import normalize_llm_json_text, parse_llm_json

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


class CompositionError(Exception):
    """Raised when LLM composition fails after retries."""


class AnswerComposerAgent:
    """S8 controlled composer: EvidenceBrief + UserNeedResidual → FinalAnswerDraft (LLM only)."""

    def __init__(self, llm_client=None) -> None:
        from app.llm_client import LLMClient

        self.llm = llm_client or LLMClient()
        self.citation_policy = CitationPolicy.for_composition()

    async def compose(self, state: TravelAgentState, arguments: dict) -> FinalAnswerDraft:
        bundle = self._build_input_bundle(state, arguments)
        if bundle.get("compose_mode") == "nearby_guided":
            return await self._compose_nearby_guided(state, bundle)
        if bundle.get("compose_mode") == "fact_lookup_guided":
            return await self._compose_fact_lookup_guided(state, bundle)
        if bundle.get("compose_mode") == "place_disambiguation":
            return await self._compose_place_disambiguation(state, bundle)

        if not self.llm._should_use_anthropic():
            if bundle.get("has_actionable_evidence"):
                fallback = self._evidence_fallback_draft(bundle)
                fallback.answer_text = fallback.render_text().strip()
                TraceRecorder.add(state, "✓ AnswerComposition 证据兜底合成（无 LLM）")
                return fallback
            TraceRecorder.add(state, "⚠ AnswerComposition 合成服务不可用（无 LLM）")
            return self._infrastructure_error_draft(bundle, RuntimeError("LLM client not initialized"))

        last_error: Exception | None = None
        last_reject_reason: str | None = None
        for attempt in range(2):
            try:
                draft = await self._llm_compose(bundle)
                draft, postprocess_note = self._postprocess_draft(draft, bundle)
                if postprocess_note:
                    logger.info("AnswerComposer postprocess: %s", postprocess_note)
                if self._accept_draft(draft, bundle):
                    draft.answer_text = draft.render_text().strip()
                    TraceRecorder.add(state, "✓ AnswerComposition 由 LLM 合成")
                    return draft
                last_reject_reason = self._reject_reason(draft, bundle)
                logger.warning(
                    "AnswerComposer LLM draft rejected (attempt %s): %s",
                    attempt + 1,
                    last_reject_reason,
                )
            except Exception as exc:
                last_error = exc
                logger.warning("AnswerComposer LLM attempt %s failed: %s", attempt + 1, exc)
                if attempt == 0:
                    bundle = {
                        **bundle,
                        "json_repair_hint": (
                            "Previous response was invalid JSON; return valid FinalAnswerDraft JSON only. "
                            "cited_evidence_ids must use full evidence_id strings from curated_claims."
                        ),
                    }

        if bundle.get("has_actionable_evidence"):
            fallback = self._evidence_fallback_draft(bundle)
            fallback, _ = self._postprocess_draft(fallback, bundle)
            if self._accept_draft(fallback, bundle):
                fallback.answer_text = fallback.render_text().strip()
                TraceRecorder.add(state, "✓ AnswerComposition 证据兜底合成（LLM 未通过校验）")
                state.limitations.append("答案由证据摘要自动生成（LLM 合成未通过校验）。")
                return fallback

        TraceRecorder.add(state, "⚠ AnswerComposition 合成服务不可用")
        state.limitations.append("答案合成服务暂时不可用，请稍后重试。")
        return self._infrastructure_error_draft(bundle, last_error or RuntimeError(last_reject_reason or "rejected"))

    def _build_input_bundle(self, state: TravelAgentState, arguments: dict) -> dict:
        evidence = state.evidence or []
        brief: EvidenceBrief | None = state.evidence_brief
        if brief is None and isinstance(arguments.get("evidence_brief"), dict):
            brief = EvidenceBrief.model_validate(arguments["evidence_brief"])
        residual: UserNeedResidual | None = state.user_need_residual

        claim_rows = []
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            for claim in ev.claims:
                claim_rows.append(
                    {
                        "evidence_id": ev.evidence_id,
                        "source_name": ev.source_name,
                        "place_name": ev.place_name,
                        "claim_type": claim.claim_type.value,
                        "value": str(claim.value),
                        "confidence": claim.confidence,
                        "is_search_miss": is_search_miss_value(str(claim.value)),
                    }
                )

        curated_claims = []
        if brief:
            curated_claims = [c.model_dump() for c in brief.curated_claims]
        compose_mode = arguments.get("compose_mode", "advisory")
        compare_places = list(arguments.get("place_names") or [])
        if compose_mode == "compare" and curated_claims:
            if not compare_places and state.semantic_frame and state.semantic_frame.entities.places:
                compare_places = list(state.semantic_frame.entities.places)
            summarized = summarize_comparison_claims_for_compose(
                curated_claims,
                compare_places,
            )
            if summarized:
                curated_claims = summarized
        actionable_claims = [r for r in claim_rows if not r.get("is_search_miss")]
        if brief and curated_claims:
            actionable_claims = curated_claims
        elif brief and brief.curated_claims:
            actionable_claims = [c.model_dump() for c in brief.curated_claims]

        overall_confidence = brief.overall_confidence if brief else 0.0
        if not brief and actionable_claims:
            overall_confidence = sum(
                float(r.get("confidence", 0.5)) for r in actionable_claims
            ) / len(actionable_claims)

        report = state.evidence_decision_report
        claim_decisions = []
        if report:
            claim_decisions = [
                {
                    "claim_type": d.claim_type,
                    "adoption": d.adoption,
                    "coverage_quality": d.coverage_quality,
                    "confidence": d.confidence,
                    "limitations": d.limitations,
                    "adopted_evidence_ids": d.adopted_evidence_ids,
                    "reason": d.reason,
                }
                for d in report.claim_decisions
            ]

        slim_brief = None
        if brief:
            slim_brief = {
                "target_label": brief.target_label,
                "curated_claims": curated_claims,
                "coverage_gaps": list(brief.coverage_gaps),
                "conflict_notes": list(brief.conflict_notes),
                "overall_confidence": brief.overall_confidence,
            }

        return {
            "compose_mode": compose_mode,
            "target_label": arguments.get("target_label") or arguments.get("place_name") or "目的地",
            "user_need_residual": residual.model_dump() if residual else None,
            "evidence_brief": slim_brief,
            "curated_claims": curated_claims,
            "overall_confidence": overall_confidence,
            "coverage_gaps": list(brief.coverage_gaps) if brief else [],
            "conflict_notes": list(brief.conflict_notes) if brief else [],
            "fact_decompositions": list(brief.fact_decompositions) if brief else [],
            "evidence_claims": [] if curated_claims else claim_rows[:40],
            "actionable_evidence_claims": actionable_claims,
            "has_actionable_evidence": bool(actionable_claims)
            or bool(brief and brief.curated_claims),
            "evidence_ids": [ev.evidence_id for ev in evidence if isinstance(ev, Evidence)],
            "citable_evidence_refs": self._citable_evidence_refs(evidence, actionable_claims),
            "limitations": list(state.limitations),
            "citation_policy": self.citation_policy.model_dump(),
            "citation_rules": self.citation_policy.to_prompt_rules(),
            "response_contract": (
                state.response_contract.model_dump() if state.response_contract else None
            ),
            "coverage_report": (
                state.coverage_report.model_dump() if state.coverage_report else None
            ),
            "composition_rules": self._composition_rules(
                state, overall_confidence, brief, compose_mode=compose_mode
            ),
            "style_prompt_fragment": self._style_prompt_fragment(state, compose_mode=compose_mode),
            "itinerary_plan": (
                arguments["plan"].model_dump()
                if arguments.get("plan") and hasattr(arguments["plan"], "model_dump")
                else arguments.get("plan")
            ),
            "compare_place_names": arguments.get("place_names"),
            "evidence_decision_report": report.model_dump() if report else None,
            "claim_decisions": claim_decisions,
            **self._disambiguation_bundle_fields(state, arguments, compose_mode),
            **self._nearby_guided_bundle_fields(state, arguments, compose_mode),
            **self._fact_lookup_guided_bundle_fields(state, arguments, compose_mode),
        }

    @staticmethod
    def _nearby_guided_bundle_fields(
        state: TravelAgentState,
        arguments: dict,
        compose_mode: str,
    ) -> dict:
        if compose_mode != "nearby_guided" and not arguments.get("nearby_guided_presentation"):
            return {}
        from app.orchestrator.nearby_guided_composition import build_nearby_guided_presentation

        presentation = arguments.get("nearby_guided_presentation") or build_nearby_guided_presentation(
            state
        )
        return {
            "nearby_guided_presentation": presentation,
            "has_actionable_evidence": bool(
                presentation.get("area_nearby_clues")
            ),
        }

    async def _compose_nearby_guided(
        self,
        state: TravelAgentState,
        bundle: dict,
    ) -> FinalAnswerDraft:
        from app.orchestrator.nearby_guided_composition import build_nearby_guided_draft

        fallback = build_nearby_guided_draft(state, bundle.get("nearby_guided_presentation"))
        if not self.llm._should_use_anthropic():
            TraceRecorder.add(state, "✓ AnswerComposition 片区周边引导（无 LLM）")
            return fallback

        try:
            draft = await self._llm_compose(bundle)
            draft, _ = self._postprocess_draft(draft, bundle)
            if self._accept_draft(draft, bundle):
                draft.answer_text = draft.render_text().strip()
                draft.compose_mode = "nearby_guided"
                TraceRecorder.add(state, "✓ AnswerComposition 片区周边引导（LLM）")
                return draft
        except Exception as exc:
            logger.warning("AnswerComposer nearby_guided LLM failed: %s", exc)

        TraceRecorder.add(state, "✓ AnswerComposition 片区周边引导（兜底模板）")
        return fallback

    @staticmethod
    def _fact_lookup_guided_bundle_fields(
        state: TravelAgentState,
        arguments: dict,
        compose_mode: str,
    ) -> dict:
        if compose_mode != "fact_lookup_guided" and not arguments.get("fact_lookup_presentation"):
            return {}
        from app.orchestrator.fact_lookup_guided_composition import build_fact_lookup_presentation

        presentation = arguments.get("fact_lookup_presentation") or build_fact_lookup_presentation(state)
        return {
            "fact_lookup_presentation": presentation,
            "has_actionable_evidence": bool(presentation.get("fact_clues"))
            or bool(presentation.get("ticket_price_facts"))
            or bool(presentation.get("opening_hours_facts"))
            or bool(presentation.get("ticket_area_policy")),
        }

    async def _compose_fact_lookup_guided(
        self,
        state: TravelAgentState,
        bundle: dict,
    ) -> FinalAnswerDraft:
        from app.orchestrator.fact_lookup_guided_composition import build_fact_lookup_draft

        fallback = build_fact_lookup_draft(state, bundle.get("fact_lookup_presentation"))
        if self._should_use_deterministic_ticket_fact_draft(bundle):
            fallback.answer_text = fallback.render_text().strip()
            TraceRecorder.add(state, "✓ AnswerComposition 票价结构化证据模板")
            return fallback
        if not self.llm._should_use_anthropic():
            TraceRecorder.add(state, "✓ AnswerComposition 硬事实引导（无 LLM）")
            return fallback

        try:
            draft = await self._llm_compose(bundle)
            draft, _ = self._postprocess_draft(draft, bundle)
            if self._accept_draft(draft, bundle):
                draft.answer_text = draft.render_text().strip()
                draft.compose_mode = "fact_lookup_guided"
                TraceRecorder.add(state, "✓ AnswerComposition 硬事实引导（LLM）")
                return draft
        except Exception as exc:
            logger.warning("AnswerComposer fact_lookup_guided LLM failed: %s", exc)

        TraceRecorder.add(state, "✓ AnswerComposition 硬事实引导（兜底模板）")
        return fallback

    @staticmethod
    def _should_use_deterministic_ticket_fact_draft(bundle: dict) -> bool:
        presentation = bundle.get("fact_lookup_presentation") or {}
        ticket_facts = presentation.get("ticket_price_facts") or []
        if not AnswerComposerAgent._has_structured_ticket_authority(ticket_facts):
            return False
        ticket_claims = {
            "ticket_price",
            "entrance_ticket_price",
            "boat_ticket_price",
            "shuttle_bus_ticket_price",
            "cable_car_ticket_price",
        }
        if str(presentation.get("primary_fact_need") or "") not in ticket_claims:
            return False
        for claim in presentation.get("lookup_claims") or []:
            if not isinstance(claim, dict):
                continue
            claim_type = str(claim.get("claim_type") or "")
            if claim_type and claim_type not in ticket_claims:
                return False
        return True

    @staticmethod
    def _has_structured_ticket_authority(ticket_facts: list) -> bool:
        trusted_sources = {
            "official",
            "official_page",
            "government",
            "tourism_board",
        }
        for fact in ticket_facts or []:
            if not isinstance(fact, dict):
                continue
            source_class = str(fact.get("source_class") or "").lower()
            strength = str(fact.get("evidence_strength") or "").lower()
            price = fact.get("adult_price")
            has_amount = isinstance(price, int | float)
            if source_class in trusted_sources and strength in {"strong", "partial"} and has_amount:
                return True
        return False

    @staticmethod
    def _disambiguation_bundle_fields(
        state: TravelAgentState,
        arguments: dict,
        compose_mode: str,
    ) -> dict:
        if compose_mode != "place_disambiguation" and not arguments.get("disambiguation_presentation"):
            return {}
        from app.orchestrator.place_disambiguation_composition import build_disambiguation_presentation

        presentation = arguments.get("disambiguation_presentation") or build_disambiguation_presentation(
            state
        )
        return {
            "disambiguation_presentation": presentation,
            "has_actionable_evidence": bool(presentation.get("options")),
        }

    async def _compose_place_disambiguation(
        self,
        state: TravelAgentState,
        bundle: dict,
    ) -> FinalAnswerDraft:
        from app.orchestrator.place_disambiguation_composition import build_disambiguation_draft

        fallback = build_disambiguation_draft(state, bundle.get("disambiguation_presentation"))
        if not self.llm._should_use_anthropic():
            TraceRecorder.add(state, "✓ AnswerComposition 地点消歧呈现（无 LLM）")
            return fallback

        try:
            draft = await self._llm_compose(bundle)
            draft, _ = self._postprocess_draft(draft, bundle)
            if self._accept_draft(draft, bundle):
                draft.answer_text = draft.render_text().strip()
                draft.compose_mode = "place_disambiguation"
                TraceRecorder.add(state, "✓ AnswerComposition 地点消歧呈现（LLM）")
                return draft
        except Exception as exc:
            logger.warning("AnswerComposer place_disambiguation LLM failed: %s", exc)

        TraceRecorder.add(state, "✓ AnswerComposition 地点消歧呈现（兜底模板）")
        return fallback

    def _composition_rules(
        self,
        state: TravelAgentState,
        overall_confidence: float,
        brief: EvidenceBrief | None,
        *,
        compose_mode: str = "advisory",
    ) -> list[str]:
        rules = [
            "user_need_residual describes what the user wants to know and their constraints — NOT verified facts.",
            "Never treat prices, hours, or place facts from user_need_residual or user query as confirmed.",
            "Place names in the answer must come from evidence_brief.curated_claims.place_name or target_label derived from evidence.",
            "Distinguish verified facts from model-prior / general-context statements.",
            "Do not invent unsupported claims for missing required evidence.",
            "You MUST surface valuable clues from evidence_brief.curated_claims with confidence levels.",
            "Never return a one-line stub or truncated sentence.",
            "cited_evidence_ids: copy full evidence_id from curated_claims — never shorten UUIDs.",
            "S8 must follow claim_decisions.adoption from evidence_decision_report — do NOT re-judge evidence.",
        ]
        if compose_mode == "place_disambiguation":
            rules.extend(
                [
                    "compose_mode is place_disambiguation: list EVERY option in disambiguation_presentation.options.",
                    "For each option show location fields and evidence_clues; do not merge clues across regions.",
                    "If has_clues_for_question is false for an option, state that no adoptable evidence was found for question_label.",
                    "Include shared_clues in a separate section when non-empty.",
                    "End with selection_prompt; set next_state intent to user picking an index or province/city.",
                    "Do NOT answer the factual question as if one place were already confirmed.",
                ]
            )
            return rules
        if compose_mode == "fact_lookup_guided":
            rules.extend(
                [
                    "compose_mode is fact_lookup_guided: LEAD with a one-sentence factual conclusion (price/hours/policy).",
                    "Follow fact_lookup_presentation.claim_decision.adoption_level — do NOT upgrade or downgrade S7.",
                    "strong: cite official/structured source; partial: add 未完全官方确认; candidate_only: 官方未确认, not a definitive price/hour.",
                    "no_evidence/rejected/weak or can_answer_directly=false: headline must be 无法确认 — never invent numbers.",
                    "If must_show_limitation=true, include a limitations section with evidence gaps.",
                    "Use opening_hours_facts when present; respect evidence_strength per row.",
                    "List every fact_clues entry with source_name; mark 官方 when official=true.",
                    "Do NOT recommend food, routes, or weather unless asked.",
                ]
            )
            return rules
        if compose_mode == "nearby_guided":
            rules.extend(
                [
                    "compose_mode is nearby_guided: LEAD with area_nearby_clues — full numbered list with sources; use area_nearby_clues_by_need for multi-category queries.",
                    "Answer the user's nearby category (food, toilet, parking, etc.) — do NOT substitute a different POI type.",
                    "Do NOT refuse to answer when area_nearby_clues is non-empty.",
                    "Disambiguation is secondary; optional short section at end only.",
                    "Every POI name must trace to area_nearby_clues or curated_claims.",
                ]
            )
            return rules
        profile = state.intent_profile
        if profile and profile.answer_style == AnswerStyle.COMPARISON:
            rules.extend(
                [
                    "Structure the answer with one subsection per place, then a short comparison summary.",
                    "For each place, list crowd / access / review clues from curated_claims when present.",
                    "If a dimension lacks strong evidence, say 证据不足 for that dimension only — not that all evidence is missing.",
                    "Complete every bullet and section; never stop mid-sentence.",
                ]
            )
        rules.extend(self._adoption_rules(state))
        rules.extend(self._style_rules(state))
        from app.orchestrator.place_disambiguation_guard import extract_place_candidates

        if extract_place_candidates(list(state.evidence or [])):
            rules.append(
                "Multiple同名 places detected: present ticket/price clues as 候选信息 per source, "
                "note which region each clue may refer to, and ask which 五彩滩/place the user means."
            )
        if brief and brief.fact_decompositions:
            rules.extend(
                [
                    "evidence_brief.fact_decompositions lists decomposed tiers "
                    "(ticket packages, visit-duration scopes, distance with origin/destination).",
                    "Present EACH tier with its conditions — differences are scope/type, NOT 'unknown'.",
                    "Mark outliers separately with low confidence; do not let one outlier block presenting agreed tiers.",
                ]
            )
        if overall_confidence < 0.55 or (brief and brief.coverage_gaps):
            rules.append(
                "overall_confidence is low or required claims are uncovered — prominently state 证据不足/未核实 in the answer body."
            )
        frame = state.semantic_frame
        if frame and (
            frame.task_family.value == "fact_lookup" or frame.decision_type.value == "fact_lookup"
        ):
            rules.extend(
                [
                    "User asked a hard-fact question; always summarize retrieved snippets with confidence.",
                    "If official confirmation is missing, present partial search clues and state the gap clearly.",
                ]
            )
        contract = state.response_contract
        if contract:
            cp = contract.composition_policy
            if cp.must_cite_evidence:
                rules.append("Cite evidence_ids for factual claims.")
            if cp.distinguish_fact_vs_prior:
                rules.append("Label model-prior or general seasonal context as low-confidence background.")
            if cp.forbid_unsupported_claims:
                rules.append("Forbidden: stating official facts without supporting evidence.")
        for item in state.coverage_report.items if state.coverage_report else []:
            if not item.covered and item.missing_behavior == "answer_with_limitation":
                rules.append(f"Missing required claim {item.claim_type}: explain gap and tools tried.")
        has_evidence = any(isinstance(ev, Evidence) for ev in (state.evidence or []))
        actionable = bool(brief and brief.curated_claims) or any(
            isinstance(ev, Evidence)
            and any(not is_search_miss_value(str(c.value)) for c in ev.claims)
            for ev in (state.evidence or [])
        )
        if has_evidence and not actionable:
            rules.extend(
                [
                    "Evidence only contains search/tool misses — explain the gap honestly in Chinese.",
                    "Do NOT echo raw 'No search hits' strings as answer content.",
                    "cited_evidence_ids may be empty when there is no substantive evidence.",
                ]
            )
        return rules

    @staticmethod
    def _style_rules(state: TravelAgentState) -> list[str]:
        profile = state.intent_profile
        if not profile:
            return []
        style = profile.answer_style
        mapping: dict[AnswerStyle, list[str]] = {
            AnswerStyle.DIRECT_FACT: [
                "Lead with the factual conclusion; if evidence is missing, say 无法确认 before background.",
            ],
            AnswerStyle.ADVISORY: [
                "Lead with recommendation, then suitable/unsuitable conditions.",
            ],
            AnswerStyle.ITINERARY: [
                "Structure by time blocks or steps; avoid vague generic advice.",
            ],
            AnswerStyle.COMPARISON: [
                "Compare by consistent dimensions; refuse asymmetric guesses when one side lacks evidence.",
            ],
            AnswerStyle.RECOMMENDATION_LIST: [
                "Use a list with distance, reason, and caveats per recommendation.",
            ],
            AnswerStyle.CLARIFICATION: [
                "Ask exactly one critical clarifying question; do not answer the main question yet.",
            ],
        }
        return list(mapping.get(style, []))

    @staticmethod
    def _style_prompt_fragment(state: TravelAgentState, *, compose_mode: str = "advisory") -> str:
        if compose_mode == "place_disambiguation":
            path = PROMPTS_DIR / "composer_place_disambiguation.md"
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()
            return ""
        if compose_mode == "nearby_guided":
            path = PROMPTS_DIR / "composer_nearby_guided.md"
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()
            return ""
        if compose_mode == "fact_lookup_guided":
            path = PROMPTS_DIR / "composer_fact_lookup_guided.md"
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()
            return ""
        compose_prompts = {
            "nearby": "composer_recommendation_list.md",
            "review_insight": "composer_advisory.md",
            "realtime_status": "composer_direct_fact.md",
            "fact_lookup": "composer_direct_fact.md",
            "compare": "composer_comparison.md",
            "itinerary": "composer_itinerary.md",
            "clarification": "composer_clarification.md",
            "advisory": "composer_advisory.md",
        }
        fname = compose_prompts.get(compose_mode)
        if fname:
            path = PROMPTS_DIR / fname
            if path.is_file():
                base = path.read_text(encoding="utf-8").strip()
                if compose_mode == "nearby":
                    base += (
                        "\n\n输出须包含：名称、距离/步行或驾车时间、推荐理由、适合场景、证据限制。"
                    )
                elif compose_mode == "review_insight":
                    base += (
                        "\n\n用语示例：「可见评论倾向……」「多条游客反馈提到……」"
                        "「如果你介意 X，可能不太适合」。"
                    )
                elif compose_mode == "realtime_status":
                    base += (
                        "\n\n必须带时效说明，例如「根据目前可获取的天气预报……」"
                        "「实时人流没有可靠来源，只能结合节假日和评论信号估计……」。"
                    )
                return base
        profile = state.intent_profile
        if not profile:
            return ""
        fname = {
            AnswerStyle.DIRECT_FACT: "composer_direct_fact.md",
            AnswerStyle.ADVISORY: "composer_advisory.md",
            AnswerStyle.ITINERARY: "composer_itinerary.md",
            AnswerStyle.COMPARISON: "composer_comparison.md",
            AnswerStyle.RECOMMENDATION_LIST: "composer_recommendation_list.md",
            AnswerStyle.CLARIFICATION: "composer_clarification.md",
        }.get(profile.answer_style)
        if not fname:
            return ""
        path = PROMPTS_DIR / fname
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        return ""

    @staticmethod
    def _adoption_rules(state: TravelAgentState) -> list[str]:
        report = state.evidence_decision_report
        if not report:
            return []
        rules: list[str] = []
        for decision in report.claim_decisions:
            if decision.adoption == "candidate_only":
                rules.append(
                    f"For {decision.claim_type}: present platform/search clues only as 候选信息 — "
                    "never state as official confirmed fact."
                )
            elif decision.adoption == "refuse_to_guess":
                brief = state.evidence_brief
                has_curated = bool(
                    brief
                    and any(c.claim_type == decision.claim_type for c in brief.curated_claims)
                )
                if (
                    state.intent_profile
                    and state.intent_profile.primary_intent.value == "comparison"
                    and has_curated
                ):
                    rules.append(
                        f"For {decision.claim_type}: coverage is weak — present partial curated clues "
                        "with limitations instead of claiming zero evidence."
                    )
                else:
                    rules.append(
                        f"For {decision.claim_type}: explicitly state you cannot confirm; do not guess."
                    )
            elif decision.adoption == "ask_clarification":
                rules.append(
                    f"For {decision.claim_type}: ask the user for clarification instead of guessing."
                )
            elif decision.adoption == "omit":
                rules.append(f"For {decision.claim_type}: omit this topic from the answer body.")
            elif decision.adoption == "adopt_with_limitation":
                rules.append(
                    f"For {decision.claim_type}: answer with stated limitations: "
                    + "; ".join(decision.limitations[:2])
                    if decision.limitations
                    else "evidence incomplete"
                )
        return rules

    async def _llm_compose(self, bundle: dict) -> FinalAnswerDraft:
        style_fragment = bundle.get("style_prompt_fragment", "")
        system = (
            "You compose travel answers grounded in evidence_brief.curated_claims and user_need_residual.\n"
            "Return ONLY valid JSON matching FinalAnswerDraft:\n"
            "{headline, conclusion, sections:[{title,bullets:[string,...]}], limitations, cited_evidence_ids, compose_mode}\n"
            "Do NOT duplicate content in answer_text; leave answer_text empty — rendering uses sections.\n"
            "sections[].bullets must be plain strings (not objects); put evidence_id values in cited_evidence_ids.\n"
            "cited_evidence_ids must use exact evidence_id strings from citable_evidence_refs or curated_claims (full UUIDs).\n"
        )
        if style_fragment:
            system += f"\n{style_fragment}\n"
        system += (
            "Rules:\n"
            + "\n".join(f"- {r}" for r in bundle["citation_rules"])
            + "\n"
            + "\n".join(f"- {r}" for r in bundle.get("composition_rules", []))
        )
        user = json.dumps(bundle, ensure_ascii=False)
        from app.config import get_settings

        settings = get_settings()
        max_tokens = int(settings.llm_max_output_tokens)
        raw = await self.llm.complete(
            system=system,
            user=user,
            max_tokens=max_tokens,
            json_only=True,
        )
        try:
            data = parse_llm_json(raw)
        except json.JSONDecodeError as exc:
            normalized = normalize_llm_json_text(raw)
            logger.warning(
                "AnswerComposer JSON parse failed (%s); normalized preview: %.200s",
                exc,
                normalized,
            )
            raise
        data = self._normalize_draft_payload(data)
        return FinalAnswerDraft.model_validate(data)

    @staticmethod
    def _normalize_draft_payload(data: dict) -> dict:
        """Coerce LLM variants (e.g. bullets as {content, evidence_id}) into schema shape."""
        if not isinstance(data, dict):
            return data

        raw_limitations = data.get("limitations") or []
        if isinstance(raw_limitations, str):
            raw_limitations = [
                part.strip(" -\t")
                for part in re.split(r"[\n；;]+", raw_limitations)
                if part.strip(" -\t")
            ]
        elif not isinstance(raw_limitations, list):
            raw_limitations = [str(raw_limitations)]
        from app.orchestrator.response_sanitizer import sanitize_limitations

        limitations = sanitize_limitations([str(x) for x in raw_limitations], max_items=5)
        cited = [
            str(x).strip()
            for x in (data.get("cited_evidence_ids") or [])
            if x and str(x).strip()
        ]
        sections = data.get("sections")
        if not isinstance(sections, list):
            return {**data, "limitations": limitations, "cited_evidence_ids": cited}

        normalized_sections: list[dict] = []
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            bullets_out: list[str] = []
            for item in sec.get("bullets") or []:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        bullets_out.append(text)
                    continue
                if isinstance(item, dict):
                    text = str(
                        item.get("content")
                        or item.get("text")
                        or item.get("bullet")
                        or item.get("value")
                        or ""
                    ).strip()
                    eid = item.get("evidence_id") or item.get("evidenceId") or item.get("citation")
                    if text:
                        bullets_out.append(text)
                    if eid:
                        token = str(eid).strip()
                        if token and token not in cited:
                            cited.append(token)
                    continue
                text = str(item).strip()
                if text:
                    bullets_out.append(text)
            normalized_sections.append({**sec, "bullets": bullets_out})

        return {
            **data,
            "limitations": limitations,
            "sections": normalized_sections,
            "cited_evidence_ids": cited,
        }

    def _accept_draft(self, draft: FinalAnswerDraft, bundle: dict) -> bool:
        return (
            self._validate_draft(draft, bundle)
            and self._has_substantive_content(draft)
            and not self._looks_incomplete_answer(draft)
        )

    def _reject_reason(self, draft: FinalAnswerDraft, bundle: dict) -> str:
        if not self._validate_draft(draft, bundle):
            return "validation_failed"
        if not self._has_substantive_content(draft):
            return "no_substantive_content"
        if self._looks_incomplete_answer(draft):
            return "incomplete_answer"
        return "unknown"

    def _postprocess_draft(
        self,
        draft: FinalAnswerDraft,
        bundle: dict,
    ) -> tuple[FinalAnswerDraft, str | None]:
        allowed_ids = list(bundle.get("evidence_ids", []))
        notes: list[str] = []

        if draft.cited_evidence_ids:
            resolved, unresolved = self._normalize_cited_evidence_ids(draft.cited_evidence_ids, allowed_ids)
            if resolved and resolved != draft.cited_evidence_ids:
                notes.append(f"resolved_citations:{len(resolved)}")
            if unresolved:
                notes.append(f"unresolved_citations:{unresolved}")
            draft.cited_evidence_ids = resolved

        if (
            self.citation_policy.require_evidence_citations
            and bundle.get("has_actionable_evidence")
            and not draft.cited_evidence_ids
        ):
            inferred = self._infer_cited_evidence_ids(draft, bundle)
            if inferred:
                draft.cited_evidence_ids = inferred
                notes.append(f"inferred_citations:{len(inferred)}")

        note = "; ".join(notes) if notes else None
        return draft, note

    @staticmethod
    def _citable_evidence_refs(evidence: list, actionable_claims: list[dict]) -> list[dict]:
        refs: list[dict] = []
        seen: set[str] = set()
        for claim in actionable_claims:
            eid = str(claim.get("evidence_id", "")).strip()
            if not eid or eid in seen:
                continue
            seen.add(eid)
            refs.append(
                {
                    "evidence_id": eid,
                    "source_name": claim.get("source_name"),
                    "claim_type": claim.get("claim_type"),
                    "value_preview": str(claim.get("value", ""))[:120],
                }
            )
        if refs:
            return refs
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            sample = ""
            for claim in ev.claims:
                if not is_search_miss_value(str(claim.value)):
                    sample = str(claim.value)[:120]
                    break
            refs.append(
                {
                    "evidence_id": ev.evidence_id,
                    "source_name": ev.source_name,
                    "value_preview": sample,
                }
            )
        return refs

    @staticmethod
    def _resolve_evidence_id(raw_id: str, allowed_ids: list[str]) -> str | None:
        token = raw_id.strip()
        if not token:
            return None
        if token in allowed_ids:
            return token
        lower_map = {eid.lower(): eid for eid in allowed_ids}
        if token.lower() in lower_map:
            return lower_map[token.lower()]
        prefix_matches = [eid for eid in allowed_ids if eid.lower().startswith(token.lower())]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        if len(prefix_matches) > 1:
            logger.warning(
                "Ambiguous evidence id prefix %r matches %d ids; skipping",
                token,
                len(prefix_matches),
            )
        return None

    @staticmethod
    def _normalize_cited_evidence_ids(
        cited_ids: list[str],
        allowed_ids: list[str],
    ) -> tuple[list[str], list[str]]:
        resolved: list[str] = []
        unresolved: list[str] = []
        for raw in cited_ids:
            full = AnswerComposerAgent._resolve_evidence_id(raw, allowed_ids)
            if full:
                if full not in resolved:
                    resolved.append(full)
            else:
                unresolved.append(raw)
        return resolved, unresolved

    @staticmethod
    def _infer_cited_evidence_ids(draft: FinalAnswerDraft, bundle: dict) -> list[str]:
        body = "\n".join(
            [
                draft.answer_text or "",
                draft.conclusion or "",
                draft.headline or "",
                *[b for s in draft.sections for b in s.bullets],
            ]
        )
        if not body.strip():
            return []

        inferred: list[str] = []
        allowed = set(bundle.get("evidence_ids", []))
        for claim in bundle.get("actionable_evidence_claims", []):
            eid = str(claim.get("evidence_id", "")).strip()
            if not eid or eid not in allowed:
                continue
            value = str(claim.get("value", "")).strip()
            if len(value) >= 3 and value in body:
                if eid not in inferred:
                    inferred.append(eid)
        if inferred:
            return inferred

        for claim in bundle.get("actionable_evidence_claims", []):
            eid = str(claim.get("evidence_id", "")).strip()
            if eid and eid in allowed and eid not in inferred:
                inferred.append(eid)
        return inferred

    def _validate_draft(self, draft: FinalAnswerDraft, bundle: dict) -> bool:
        if bundle.get("compose_mode") == "place_disambiguation":
            return bool(draft.conclusion or draft.answer_text or draft.sections)
        if bundle.get("compose_mode") == "nearby_guided":
            return bool(draft.sections or draft.conclusion or draft.answer_text)
        allowed_ids = set(bundle.get("evidence_ids", []))
        if draft.cited_evidence_ids and not set(draft.cited_evidence_ids).issubset(allowed_ids):
            logger.warning("Draft cites unknown evidence ids: %s", draft.cited_evidence_ids)
            return False
        if self.citation_policy.require_evidence_citations and bundle.get("has_actionable_evidence"):
            if not draft.cited_evidence_ids and draft.conclusion:
                return False
        return bool(draft.conclusion or draft.answer_text or draft.sections)

    @staticmethod
    def _evidence_fallback_draft(bundle: dict) -> FinalAnswerDraft:
        target = bundle.get("target_label", "目的地")
        compose_mode = bundle.get("compose_mode", "advisory")
        claims = bundle.get("actionable_evidence_claims") or []
        if compose_mode == "place_disambiguation":
            from app.orchestrator.place_disambiguation_composition import (
                build_disambiguation_draft_from_bundle,
            )

            return build_disambiguation_draft_from_bundle(bundle)
        if compose_mode == "nearby_guided":
            from app.orchestrator.nearby_guided_composition import build_nearby_guided_draft_from_bundle

            return build_nearby_guided_draft_from_bundle(bundle)
        if compose_mode == "compare":
            return AnswerComposerAgent._comparison_fallback_draft(bundle)

        bullets: list[str] = []
        cited: list[str] = []
        for claim in claims[:8]:
            conf = float(claim.get("confidence", 0.5))
            value = str(claim.get("value", "")).strip()
            if not value:
                continue
            source = claim.get("source_name") or "检索来源"
            bullets.append(f"{value}（来源：{source}，置信度 {conf:.0%}）")
            eid = str(claim.get("evidence_id", "")).strip()
            if eid and eid not in cited:
                cited.append(eid)

        low_conf = float(bundle.get("overall_confidence", 0))
        gap_prefix = "【证据不足/未核实】" if low_conf < 0.55 or bundle.get("coverage_gaps") else ""
        if bullets:
            body = f"{gap_prefix}关于{target}：{'；'.join(bullets)}。建议出发前再核实官方渠道。"
        else:
            body = f"{gap_prefix}关于{target}：未能从检索获得足够可引用信息，建议查阅官方渠道确认。"

        limitations = list(bundle.get("limitations", []))
        limitations.extend(bundle.get("coverage_gaps") or [])
        limitations.extend(bundle.get("conflict_notes") or [])

        return FinalAnswerDraft(
            headline=f"关于 {target}",
            conclusion=body,
            sections=[FinalAnswerSection(title="检索线索", bullets=bullets or [body])],
            limitations=limitations,
            cited_evidence_ids=cited,
            answer_text=body,
            compose_mode=compose_mode,
        )

    @staticmethod
    def _comparison_fallback_draft(bundle: dict) -> FinalAnswerDraft:
        places = list(bundle.get("compare_place_names") or [])
        claims = bundle.get("actionable_evidence_claims") or []
        target = bundle.get("target_label", " vs ".join(places) if places else "比较")
        sections: list[FinalAnswerSection] = []
        cited: list[str] = []
        low_conf = float(bundle.get("overall_confidence", 0))
        gap_prefix = "【证据不足/未核实】" if low_conf < 0.55 or bundle.get("coverage_gaps") else ""

        for place in places or [target]:
            bullets: list[str] = []
            for claim in claims:
                claim_place = str(claim.get("place_name") or "").strip()
                if claim_place and not places_match(place, claim_place):
                    continue
                if not claim_place:
                    value = str(claim.get("value", "")).strip()
                    if value and place not in value and not places_match(place, value):
                        continue
                value = str(claim.get("value", "")).strip()
                if not value:
                    continue
                dim = str(claim.get("claim_type", "线索"))
                conf = float(claim.get("confidence", 0.5))
                bullets.append(f"【{dim}】{value[:200]}（置信度 {conf:.0%}）")
                eid = str(claim.get("evidence_id", "")).strip()
                if eid and eid not in cited:
                    cited.append(eid)
            if not bullets:
                bullets.append("暂无足够可引用线索，建议查阅官方或近期游记核实。")
            sections.append(FinalAnswerSection(title=place, bullets=bullets))

        conclusion = (
            f"{gap_prefix}基于现有检索线索，对{'与'.join(places)}做维度对比；"
            "拥挤度与交通信息仍可能不完整，请结合出行季节再核实。"
        )
        body_parts = [f"### {target}", "", conclusion]
        for section in sections:
            body_parts.extend(["", f"#### {section.title}", *[f"- {b}" for b in section.bullets]])
        answer_text = "\n".join(body_parts).strip()

        limitations = list(bundle.get("limitations", []))
        limitations.extend(bundle.get("coverage_gaps") or [])
        limitations.extend(bundle.get("conflict_notes") or [])

        return FinalAnswerDraft(
            headline=f"{target} 对比",
            conclusion=conclusion,
            sections=sections,
            limitations=limitations,
            cited_evidence_ids=cited,
            answer_text=answer_text,
            compose_mode="compare",
        )

    @staticmethod
    def _has_substantive_content(draft: FinalAnswerDraft) -> bool:
        if (draft.answer_text or draft.conclusion or draft.headline or "").strip():
            return True
        for section in draft.sections:
            if section.title.strip() or any(b.strip() for b in section.bullets):
                return True
        return False

    @staticmethod
    def _looks_incomplete_answer(draft: FinalAnswerDraft) -> bool:
        chunks: list[str] = []
        for part in (draft.answer_text, draft.conclusion):
            if part and str(part).strip():
                chunks.append(str(part).strip())
        for section in draft.sections:
            chunks.extend(str(b).strip() for b in section.bullets if str(b).strip())

        if not chunks:
            return True

        for text in chunks:
            stripped = text.strip()
            if len(stripped) < 12:
                continue
            if not re.search(r"[。！？?!）%\n]$", stripped):
                return True
            if re.search(r"(，有|：有|——|…|\.\.\.|\d{4})$", stripped):
                return True
            if re.search(r"[\[\(（「『]$", stripped):
                return True
        return False

    @staticmethod
    def _infrastructure_error_draft(bundle: dict, error: Exception | None) -> FinalAnswerDraft:
        target = bundle.get("target_label", "目的地")
        msg = (
            f"关于「{target}」的答案暂时无法生成：合成服务不可用。"
            "请稍后重试，或查阅官方渠道确认。"
        )
        if error:
            logger.debug("Infrastructure composition error: %s", error)
        return FinalAnswerDraft(
            headline=f"关于 {target}",
            conclusion=msg,
            sections=[FinalAnswerSection(title="服务提示", bullets=[msg])],
            limitations=list(bundle.get("limitations", [])),
            cited_evidence_ids=[],
            answer_text=msg,
            compose_mode=bundle.get("compose_mode", "advisory"),
        )
