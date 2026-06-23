import json
import logging
import re
from pathlib import Path

from app.orchestrator.claim_search_planner import is_search_miss_value
from app.orchestrator.trace import TraceRecorder
from app.policies.citation_policy import CitationPolicy
from app.schemas.evidence import Evidence
from app.schemas.evidence_brief import EvidenceBrief
from app.schemas.final_answer_draft import FinalAnswerDraft, FinalAnswerSection
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
        actionable_claims = [r for r in claim_rows if not r.get("is_search_miss")]
        if brief and brief.curated_claims:
            actionable_claims = curated_claims

        overall_confidence = brief.overall_confidence if brief else 0.0
        if not brief and actionable_claims:
            overall_confidence = sum(
                float(r.get("confidence", 0.5)) for r in actionable_claims
            ) / len(actionable_claims)

        return {
            "compose_mode": arguments.get("compose_mode", "advisory"),
            "target_label": arguments.get("target_label") or arguments.get("place_name") or "目的地",
            "user_need_residual": residual.model_dump() if residual else None,
            "evidence_brief": brief.model_dump() if brief else None,
            "curated_claims": curated_claims,
            "overall_confidence": overall_confidence,
            "coverage_gaps": list(brief.coverage_gaps) if brief else [],
            "conflict_notes": list(brief.conflict_notes) if brief else [],
            "evidence_claims": claim_rows,
            "actionable_evidence_claims": actionable_claims,
            "has_actionable_evidence": bool(actionable_claims),
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
            "composition_rules": self._composition_rules(state, overall_confidence, brief),
            "itinerary_plan": (
                arguments["plan"].model_dump()
                if arguments.get("plan") and hasattr(arguments["plan"], "model_dump")
                else arguments.get("plan")
            ),
            "compare_place_names": arguments.get("place_names"),
        }

    def _composition_rules(
        self,
        state: TravelAgentState,
        overall_confidence: float,
        brief: EvidenceBrief | None,
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
        ]
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

    async def _llm_compose(self, bundle: dict) -> FinalAnswerDraft:
        system = (
            "You compose travel answers grounded in evidence_brief.curated_claims and user_need_residual.\n"
            "Return ONLY valid JSON matching FinalAnswerDraft:\n"
            "{headline, conclusion, sections:[{title,bullets}], limitations, cited_evidence_ids, answer_text, compose_mode}\n"
            "cited_evidence_ids must use exact evidence_id strings from citable_evidence_refs or curated_claims (full UUIDs).\n"
            "Rules:\n"
            + "\n".join(f"- {r}" for r in bundle["citation_rules"])
            + "\n"
            + "\n".join(f"- {r}" for r in bundle.get("composition_rules", []))
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
    def _has_substantive_content(draft: FinalAnswerDraft) -> bool:
        if (draft.answer_text or draft.conclusion or draft.headline or "").strip():
            return True
        for section in draft.sections:
            if section.title.strip() or any(b.strip() for b in section.bullets):
                return True
        return False

    @staticmethod
    def _looks_incomplete_answer(draft: FinalAnswerDraft) -> bool:
        text = (draft.answer_text or draft.conclusion or draft.headline or "").strip()
        if not text:
            return True
        if len(text) < 25:
            return False
        tail = text[-24:]
        if not re.search(r"[。！？?!\n]", tail):
            return True
        if re.search(r"(官方|目前|无法|没有|尚未|是否|需要)$", text):
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
