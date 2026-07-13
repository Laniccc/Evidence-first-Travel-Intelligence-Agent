"""S7: filter and rank claims by relevance to user needs."""

from __future__ import annotations

import json
import importlib
import logging
from typing import Any

from app.evidence.evidence_model import Evidence
from app.evidence.evidence_brief_model import CuratedClaimRow

logger = logging.getLogger(__name__)


def _llm_client_class():
    return importlib.import_module("app.integrations.llm").LLMClient


def _claim_search_planner():
    return importlib.import_module("app.planning.claim_search_planner")


def _comparison_helpers():
    return importlib.import_module("app.planning.comparison_helpers")


def _parse_llm_json(raw: str):
    return importlib.import_module("app.utils.llm_json").parse_llm_json(raw)


class ClaimRelevanceFilterAgent:
    def __init__(self, llm_client=None) -> None:
        self.llm = llm_client or _llm_client_class()()

    async def run(self, state: Any, arguments: dict | None = None) -> dict:
        structured = state.structured_result or {}
        plan = structured.get("curation_plan") or arguments or {}
        needs = plan.get("needs_to_filter") or []
        if not needs and state.user_need_residual:
            needs = [n.need_type for n in state.user_need_residual.information_needs]
        if _comparison_helpers().is_comparison_mode(state):
            needs = ["crowd_level", "route_plan", "review_summary"]

        curated, excluded = self._rule_filter(state, needs)

        if self.llm._should_use_anthropic() and curated:
            try:
                llm_rows = await self._llm_refine(state, curated, needs)
                if llm_rows:
                    curated = llm_rows
            except Exception as exc:
                logger.warning("ClaimRelevanceFilter LLM refine failed: %s", exc)

        return {
            "curated_claims": [r.model_dump() for r in curated],
            "excluded_evidence_ids": excluded,
        }

    def _rule_filter(
        self,
        state: Any,
        needs: list[str],
    ) -> tuple[list[CuratedClaimRow], list[str]]:
        evidence = state.evidence
        need_set = set(needs)
        curated: list[CuratedClaimRow] = []
        excluded_ids: list[str] = []
        seen: set[str] = set()
        primary_fact_need_from_state = importlib.import_module(
            "app.orchestration.fact_lookup_policy"
        ).primary_fact_need_from_state
        ticket_relevance_score = importlib.import_module(
            "app.evidence.ticket_relevance_policy"
        ).ticket_relevance_score

        ticket_mode = primary_fact_need_from_state(state) == "ticket_price" or "ticket_price" in need_set

        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            actionable = False
            for claim in ev.claims:
                value = str(claim.value or "").strip()
                if not value or _claim_search_planner().is_search_miss_value(value):
                    continue
                ct = claim.claim_type.value
                if ticket_mode:
                    relevance = ticket_relevance_score(
                        state,
                        ct,
                        value,
                        source_name=str(ev.source_name or ""),
                        source_url=str(ev.source_url or ""),
                    )
                    if relevance < 0.5:
                        continue
                else:
                    relevance = self._relevance_score(ct, need_set, value)
                    if relevance < 0.25:
                        continue
                actionable = True
                key = f"{ev.evidence_id}:{ct}:{value[:80]}"
                if key in seen:
                    continue
                seen.add(key)
                conf = float(getattr(claim, "confidence", None) or ev.confidence or 0.5)
                curated.append(
                    CuratedClaimRow(
                        claim_type=ct,
                        value=value[:500],
                        evidence_id=ev.evidence_id,
                        source_name=ev.source_name,
                        source_url=ev.source_url,
                        confidence=conf,
                        relevance_score=relevance,
                        rationale=f"Matched needs {needs}",
                        place_name=ev.place_name,
                    )
                )
            if not actionable:
                excluded_ids.append(ev.evidence_id)

        curated.sort(key=lambda r: (r.relevance_score, r.confidence), reverse=True)
        return curated[:24], excluded_ids

    @staticmethod
    def _relevance_score(claim_type: str, needs: set[str], value: str) -> float:
        if not needs or "general" in needs:
            return 0.55
        score = 0.35
        if claim_type in needs:
            score = 0.85
        elif claim_type.replace("_candidate", "") in {n.replace("_candidate", "") for n in needs}:
            score = 0.7
        elif any(n in claim_type or claim_type in n for n in needs):
            score = 0.6
        ticket_needs = {"ticket_price", "booking_channel"}
        if needs & ticket_needs and claim_type in {
            "ticket_price",
            "ticket_price_candidate",
            "price_candidate",
            "booking_channel",
            "travel_advice",
        }:
            score = max(score, 0.65)
        review_needs = {"review_summary", "elderly_suitability", "family_friendly", "value_for_money"}
        if needs & review_needs and claim_type in {"review_summary", "review_aspect", "travel_advice"}:
            score = max(score, 0.6)
        comparison_needs = {"crowd_level", "route_plan", "review_summary", "transit"}
        if needs & comparison_needs:
            if claim_type in comparison_needs:
                score = max(score, 0.8)
            elif claim_type in {"review_summary", "review_aspect", "travel_advice"}:
                score = max(score, 0.55)
            elif claim_type in {"duration", "distance", "transit"}:
                score = max(score, 0.6)
        if "seasonal" in " ".join(needs) or "best_time" in " ".join(needs):
            if claim_type in {"seasonal_operation_status", "seasonality", "best_time_to_visit", "travel_advice"}:
                score = max(score, 0.65)
        return score

    async def _llm_refine(
        self,
        state: Any,
        rows: list[CuratedClaimRow],
        needs: list[str],
    ) -> list[CuratedClaimRow] | None:
        system = (
            "Re-rank curated travel evidence claims. Return ONLY JSON:\n"
            '{"curated_claims":[{"claim_type","value","evidence_id","relevance_score","rationale"}]}\n'
            "Keep evidence_id unchanged. Drop irrelevant rows."
        )
        payload = {
            "user_need_residual": state.user_need_residual.model_dump() if state.user_need_residual else {},
            "needs": needs,
            "candidates": [r.model_dump() for r in rows[:16]],
        }
        raw = await self.llm.complete(
            system=system,
            user=json.dumps(payload, ensure_ascii=False),
            max_tokens=1200,
            json_only=True,
        )
        data = _parse_llm_json(raw)
        bucket = data.get("curated_claims") if isinstance(data, dict) else None
        if not isinstance(bucket, list):
            return None
        by_id = {r.evidence_id: r for r in rows}
        out: list[CuratedClaimRow] = []
        for item in bucket:
            if not isinstance(item, dict):
                continue
            eid = item.get("evidence_id")
            base = by_id.get(eid)
            if not base:
                continue
            out.append(
                base.model_copy(
                    update={
                        "relevance_score": float(item.get("relevance_score", base.relevance_score)),
                        "rationale": str(item.get("rationale") or base.rationale),
                    }
                )
            )
        return out or None
