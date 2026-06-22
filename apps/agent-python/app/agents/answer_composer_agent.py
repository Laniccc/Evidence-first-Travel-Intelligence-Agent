import json
import logging
from pathlib import Path

from app.agents.composer_agent import ComposerAgent
from app.policies.citation_policy import CitationPolicy
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.final_answer_draft import FinalAnswerDraft, FinalAnswerSection
from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.review import ReviewAspectResult
from app.schemas.user_query import TravelAgentState
from app.utils.llm_json import normalize_llm_json_text, parse_llm_json

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


class AnswerComposerAgent:
    """S8 controlled composer: Evidence + FactSheet + Review + Limitations → FinalAnswerDraft."""

    def __init__(self, llm_client=None) -> None:
        from app.llm_client import LLMClient

        self.llm = llm_client or LLMClient()
        self.citation_policy = CitationPolicy.for_composition()

    async def compose(self, state: TravelAgentState, arguments: dict) -> FinalAnswerDraft:
        bundle = self._build_input_bundle(state, arguments)
        if self.llm._should_use_anthropic():
            try:
                draft = await self._llm_compose(bundle)
                if self._validate_draft(draft, bundle) and self._has_substantive_content(draft):
                    draft.answer_text = draft.render_text().strip()
                    return draft
            except Exception as exc:
                logger.warning("AnswerComposer LLM failed, using static fallback: %s", exc)
        return self._static_compose(state, arguments, bundle)

    def _build_input_bundle(self, state: TravelAgentState, arguments: dict) -> dict:
        evidence = state.evidence or []
        fact_sheet: PlaceFactSheet | None = arguments.get("fact_sheet")
        review: ReviewAspectResult | None = arguments.get("review")

        claim_rows = []
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            for claim in ev.claims:
                claim_rows.append(
                    {
                        "evidence_id": ev.evidence_id,
                        "source_name": ev.source_name,
                        "claim_type": claim.claim_type.value,
                        "value": str(claim.value),
                        "confidence": claim.confidence,
                    }
                )

        fs_dump = fact_sheet.model_dump() if isinstance(fact_sheet, PlaceFactSheet) else None
        review_dump = review.model_dump() if isinstance(review, ReviewAspectResult) else None

        return {
            "raw_query": state.raw_user_query,
            "compose_mode": arguments.get("compose_mode", "advisory"),
            "target_label": arguments.get("target_label") or arguments.get("place_name") or "目的地",
            "evidence_claims": claim_rows,
            "evidence_ids": [ev.evidence_id for ev in evidence if isinstance(ev, Evidence)],
            "fact_sheet": fs_dump,
            "review_aspects": review_dump,
            "limitations": list(state.limitations),
            "citation_policy": self.citation_policy.model_dump(),
            "citation_rules": self.citation_policy.to_prompt_rules(),
            "response_contract": (
                state.response_contract.model_dump() if state.response_contract else None
            ),
            "coverage_report": (
                state.coverage_report.model_dump() if state.coverage_report else None
            ),
            "composition_rules": self._composition_rules(state),
        }

    @staticmethod
    def _composition_rules(state: TravelAgentState) -> list[str]:
        rules = [
            "Distinguish verified facts from model-prior / general-context statements.",
            "Do not invent unsupported claims for missing required evidence.",
        ]
        contract = state.response_contract
        if not contract:
            return rules
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
        return rules

    async def _llm_compose(self, bundle: dict) -> FinalAnswerDraft:
        system = (
            "You compose travel answers grounded ONLY in provided evidence.\n"
            "Return ONLY valid JSON matching FinalAnswerDraft:\n"
            "{headline, conclusion, sections:[{title,bullets}], limitations, cited_evidence_ids, answer_text, compose_mode}\n"
            "Rules:\n"
            + "\n".join(f"- {r}" for r in bundle["citation_rules"])
        )
        user = json.dumps(bundle, ensure_ascii=False)
        raw = await self.llm.complete(system=system, user=user, max_tokens=1200)
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
        return FinalAnswerDraft.model_validate(data)

    def _validate_draft(self, draft: FinalAnswerDraft, bundle: dict) -> bool:
        allowed_ids = set(bundle.get("evidence_ids", []))
        if draft.cited_evidence_ids and not set(draft.cited_evidence_ids).issubset(allowed_ids):
            logger.warning("Draft cites unknown evidence ids: %s", draft.cited_evidence_ids)
            return False
        if self.citation_policy.require_evidence_citations and bundle.get("evidence_claims"):
            if not draft.cited_evidence_ids and draft.conclusion:
                return False
        return bool(draft.conclusion or draft.answer_text or draft.sections)

    @staticmethod
    def _has_substantive_content(draft: FinalAnswerDraft) -> bool:
        if (draft.answer_text or draft.conclusion or draft.headline or "").strip():
            return True
        for section in draft.sections:
            if section.title.strip() or any(b.strip() for b in section.bullets):
                return True
        return False

    def _static_compose(self, state: TravelAgentState, arguments: dict, bundle: dict) -> FinalAnswerDraft:
        mode = arguments.get("compose_mode", "advisory")
        evidence = [ev for ev in state.evidence if isinstance(ev, Evidence)]

        if mode == "advisory":
            text = ComposerAgent.compose_advisory(
                bundle["target_label"],
                evidence,
                state,
            )
            conclusion = self._extract_advisory_conclusion(evidence)
        elif mode == "single":
            text = ComposerAgent.compose_single(
                arguments["place_name"],
                arguments["recommendation"],
                arguments["review"],
                arguments["fact_sheet"],
                state,
            )
            conclusion = text.split("\n")[1] if "\n" in text else text[:200]
        elif mode == "crowd":
            text = ComposerAgent.compose_crowd_inquiry(
                arguments["place_name"],
                arguments["fact_sheet"],
                arguments["review"],
                state,
            )
            conclusion = text.split("\n")[0]
        elif mode == "compare":
            text = ComposerAgent.compose_compare(arguments["ranked"], state)
            conclusion = "比较结论见下文"
        elif mode == "itinerary":
            text = ComposerAgent.compose_itinerary(arguments["plan"], state)
            conclusion = "行程建议见下文"
        else:
            text = arguments.get("fallback_text", "")
            conclusion = text[:200]

        if not (text or "").strip():
            text = conclusion or "暂无足够建议。"

        return FinalAnswerDraft(
            headline=f"关于 {bundle['target_label']}",
            conclusion=conclusion or "暂无足够建议。",
            sections=[FinalAnswerSection(title="完整回答", bullets=[text])] if text else [],
            limitations=list(state.limitations),
            cited_evidence_ids=bundle.get("evidence_ids", []),
            answer_text=text,
            compose_mode=mode,
        )

    @staticmethod
    def _extract_advisory_conclusion(evidence: list[Evidence]) -> str:
        for ev in evidence:
            for claim in ev.claims:
                if claim.claim_type in {
                    ClaimType.SEASONAL_OPERATION_STATUS,
                    ClaimType.ROAD_OPENING_PERIOD,
                    ClaimType.PUBLIC_NOTICE,
                }:
                    return str(claim.value)
        for ev in evidence:
            for claim in ev.claims:
                if claim.claim_type in {
                    ClaimType.GENERAL_SEASONAL_CONTEXT,
                    ClaimType.TRAVEL_ADVICE,
                    ClaimType.SEASONALITY,
                    ClaimType.BEST_TIME_TO_VISIT,
                }:
                    return str(claim.value)
        return "暂无足够建议。"
