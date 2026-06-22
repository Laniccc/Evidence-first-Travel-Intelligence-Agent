"""Check evidence coverage against ResponseContract claim requirements."""

from __future__ import annotations

import re

from app.schemas.coverage_report import CoverageItem, CoverageReport
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.tool_trace import ToolTrace
from app.tools.tool_name_resolver import resolve_tool_name

_GENERIC_TEMPLATE_PATTERNS = re.compile(
    r"建议查阅|旅游局|气候资料|无法确认|没有具体|需进一步查询|请查询官方",
    re.I,
)

_CLAIM_TYPE_ALIASES: dict[str, frozenset[str]] = {
    "ticket_price": frozenset({ClaimType.TICKET_PRICE.value, "price_candidate"}),
    "opening_hours": frozenset(
        {ClaimType.OPENING_HOURS.value, ClaimType.OPENING_HOURS_CANDIDATE.value}
    ),
    "weather_today": frozenset({ClaimType.WEATHER.value, "weather"}),
    "forecast": frozenset({ClaimType.WEATHER.value, "weather"}),
    "weather": frozenset({ClaimType.WEATHER.value}),
    "current_crowd": frozenset({ClaimType.CROWD.value}),
    "queue_time": frozenset({ClaimType.CROWD.value}),
    "crowd_level": frozenset({ClaimType.CROWD.value}),
    "best_time_to_visit": frozenset(
        {
            ClaimType.BEST_TIME_TO_VISIT.value,
            ClaimType.SEASONALITY.value,
            ClaimType.TRAVEL_ADVICE.value,
        }
    ),
    "seasonality": frozenset({ClaimType.SEASONALITY.value, ClaimType.TRAVEL_ADVICE.value}),
    "seasonal_operation_status": frozenset(
        {
            ClaimType.SEASONAL_OPERATION_STATUS.value,
            ClaimType.ROAD_OPENING_PERIOD.value,
            ClaimType.PUBLIC_NOTICE.value,
            ClaimType.OPENING_HOURS.value,
        }
    ),
    "general_seasonal_context": frozenset(
        {ClaimType.GENERAL_SEASONAL_CONTEXT.value, ClaimType.SEASONALITY.value, ClaimType.TRAVEL_ADVICE.value}
    ),
}

_IRRELEVANT_FOR: dict[str, frozenset[str]] = {
    "ticket_price": frozenset({ClaimType.CROWD.value, ClaimType.WEATHER.value}),
    "opening_hours": frozenset({ClaimType.CROWD.value, ClaimType.WEATHER.value}),
    "best_time_to_visit": frozenset({ClaimType.CROWD.value, ClaimType.TICKET_PRICE.value}),
    "seasonal_operation_status": frozenset(
        {ClaimType.CROWD.value, ClaimType.GENERAL_SEASONAL_CONTEXT.value}
    ),
}


class EvidenceCoverageChecker:
    """Map evidence + tool traces to CoverageReport."""

    def check(
        self,
        contract: ResponseContract,
        evidence: list,
        tool_traces: list[ToolTrace],
    ) -> CoverageReport:
        items: list[CoverageItem] = []
        for req in contract.claim_requirements:
            items.append(self._evaluate_claim(req, evidence, tool_traces))

        required = [i for i, r in zip(items, contract.claim_requirements) if r.priority == "required"]
        all_required = all(i.covered for i in required) if required else True
        untried = self._untried_preferred_tools(contract, tool_traces)
        can_finish = all_required or (not untried and bool(tool_traces))
        if not all_required and untried:
            can_finish = False

        need_limits = any(
            not i.covered and contract.claim_requirements[idx].priority == "required"
            for idx, i in enumerate(items)
        )

        summary_parts = [
            f"{i.claim_type}:{'ok' if i.covered else 'missing'}({i.coverage_quality})"
            for i in items
        ]
        return CoverageReport(
            items=items,
            all_required_covered=all_required,
            can_finish_evidence_planning=can_finish,
            answer_should_include_limitations=need_limits,
            summary="; ".join(summary_parts),
        )

    def _evaluate_claim(
        self,
        req: ClaimRequirement,
        evidence: list,
        tool_traces: list[ToolTrace],
    ) -> CoverageItem:
        aliases = _CLAIM_TYPE_ALIASES.get(req.claim_type, frozenset({req.claim_type}))
        irrelevant = _IRRELEVANT_FOR.get(req.claim_type, frozenset())

        matched_ids: list[str] = []
        best_quality = "none"
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            for claim in ev.claims:
                ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
                if ct in irrelevant:
                    continue
                if ct not in aliases and req.claim_type not in ct:
                    continue
                if req.claim_type == "seasonal_operation_status" and ct == ClaimType.GENERAL_SEASONAL_CONTEXT.value:
                    continue
                if req.claim_type == "seasonal_operation_status" and ev.source_type.value == "model_prior":
                    continue
                if req.claim_type == "ticket_price" and ct == ClaimType.PRICE_CANDIDATE.value:
                    continue
                quality = self._quality_for_claim(req, claim, ev)
                if quality == "none":
                    continue
                matched_ids.append(ev.evidence_id)
                if self._quality_rank(quality) > self._quality_rank(best_quality):
                    best_quality = quality

        covered = best_quality in ("partial", "strong") or (
            req.priority == "optional" and best_quality == "weak"
        )
        if req.priority == "required" and best_quality not in ("partial", "strong"):
            covered = False

        missing_reason = None
        if not covered:
            tried = [t.tool_name for t in tool_traces if t.status in ("ok", "error")]
            missing_reason = (
                f"No qualifying evidence for {req.claim_type}; tried: {', '.join(tried) or 'none'}"
            )

        return CoverageItem(
            claim_type=req.claim_type,
            covered=covered,
            evidence_ids=matched_ids,
            missing_reason=missing_reason,
            coverage_quality=best_quality,  # type: ignore[arg-type]
            can_answer=covered or req.priority == "optional",
            missing_behavior=req.missing_behavior,
        )

    def _quality_for_claim(self, req: ClaimRequirement, claim, ev: Evidence) -> str:
        text = f"{claim.value or ''} {claim.raw_text or ''}"
        if req.claim_type in ("best_time_to_visit", "seasonality"):
            if _GENERIC_TEMPLATE_PATTERNS.search(text):
                return "weak"
            if not re.search(r"\d{1,2}月|春|夏|秋|冬|season|month", text, re.I):
                return "weak"
        if req.claim_type == "seasonal_operation_status":
            if _GENERIC_TEMPLATE_PATTERNS.search(text) and not re.search(
                r"\d{1,2}月|至|到|-", text
            ):
                return "weak"
            if re.search(r"\d{1,2}月", text):
                return "strong"
            return "partial"
        if req.claim_type == "ticket_price" and claim.claim_type.value == ClaimType.TICKET_PRICE.value:
            return "strong"
        if ev.source_type.value == "model_prior" and not req.model_prior_allowed:
            return "none"
        conf = getattr(claim, "confidence", 0.5) or 0.5
        if conf >= 0.65:
            return "strong"
        if conf >= 0.45:
            return "partial"
        return "weak"

    @staticmethod
    def _quality_rank(q: str) -> int:
        return {"none": 0, "weak": 1, "partial": 2, "strong": 3}.get(q, 0)

    @staticmethod
    def _untried_preferred_tools(
        contract: ResponseContract,
        tool_traces: list[ToolTrace],
    ) -> list[str]:
        called = {resolve_tool_name(t.tool_name) for t in tool_traces}
        pending: list[str] = []
        for req in contract.claim_requirements:
            if req.priority != "required":
                continue
            for tool in req.preferred_tools:
                resolved = resolve_tool_name(tool)
                if tool not in pending and resolved not in called:
                    pending.append(tool)
        for tool in contract.entity_policy.preferred_tools:
            resolved = resolve_tool_name(tool)
            if tool not in pending and resolved not in called:
                pending.append(tool)
        return pending
