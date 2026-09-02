"""Claim-level citation guard with a temporary legacy-call compatibility path."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.contracts.answer_claim import AnswerClaim
from app.evidence.citation import CitationCheckResult


class CitationEvidence(BaseModel):
    evidence_id: str
    source_url: str | None = None
    document_version_id: str | None = None
    version_status: str = "active"
    content_hash: str | None = None
    active_content_hash: str | None = None
    content: str | None = None
    transient: bool = False


class CitationDecision(BaseModel):
    claim_id: str
    status: Literal["supported", "unsupported_removed", "soft_claim_allowed"]
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class CitationReport(BaseModel):
    passed: bool
    safe_failure: bool
    decisions: list[CitationDecision]
    supported_claim_ids: list[str] = Field(default_factory=list)
    removed_claim_ids: list[str] = Field(default_factory=list)
    unsupported_hard_fact_count: int = 0
    citation_precision: float = 1.0


class CitationChecker:
    @classmethod
    def check(
        cls,
        *legacy_args,
        claims: list[AnswerClaim | dict] | None = None,
        evidence_index: dict[str, CitationEvidence | dict] | None = None,
        **legacy_kwargs,
    ) -> CitationReport | CitationCheckResult:
        if claims is None:
            return cls._legacy_check(*legacy_args, **legacy_kwargs)

        index = {
            key: CitationEvidence.model_validate({"evidence_id": key, **_as_dict(value)})
            for key, value in (evidence_index or {}).items()
        }
        answer_claims = [AnswerClaim.model_validate(item) for item in claims]
        decisions = [cls._check_claim(claim, index) for claim in answer_claims]
        supported = [
            item.claim_id
            for item in decisions
            if item.status in {"supported", "soft_claim_allowed"}
        ]
        removed = [
            item.claim_id for item in decisions if item.status == "unsupported_removed"
        ]
        unsupported_hard = sum(
            item.status == "unsupported_removed" for item in decisions
        )
        hard_count = sum(claim.hard_fact for claim in answer_claims)
        supported_hard = hard_count - unsupported_hard
        return CitationReport(
            passed=unsupported_hard == 0,
            safe_failure=hard_count > 0 and supported_hard == 0,
            decisions=decisions,
            supported_claim_ids=supported,
            removed_claim_ids=removed,
            unsupported_hard_fact_count=unsupported_hard,
            citation_precision=(supported_hard / hard_count if hard_count else 1.0),
        )

    @classmethod
    def _check_claim(
        cls,
        claim: AnswerClaim,
        index: dict[str, CitationEvidence],
    ) -> CitationDecision:
        if not claim.hard_fact:
            return CitationDecision(
                claim_id=claim.claim_id,
                status="soft_claim_allowed",
                reason="soft_advice_no_hard_citation_required",
                evidence_ids=claim.evidence_ids,
            )
        if not claim.evidence_ids:
            return cls._unsupported(claim, "no_evidence_ids")
        records = []
        for evidence_id in claim.evidence_ids:
            record = index.get(evidence_id)
            if record is None:
                return cls._unsupported(claim, "missing_evidence_id")
            if not record.source_url:
                return cls._unsupported(claim, "missing_source_url")
            if record.version_status not in {"active", "transient"}:
                return cls._unsupported(claim, f"invalid_version_status:{record.version_status}")
            if not record.content_hash:
                return cls._unsupported(claim, "missing_content_hash")
            if record.active_content_hash and record.content_hash != record.active_content_hash:
                return cls._unsupported(claim, "hash_mismatch")
            records.append(record)

        distinct = {
            "".join((record.content or "").casefold().split()) for record in records
        }
        if len(distinct) > 1 and not claim.conflict_disclosed:
            return cls._unsupported(claim, "unreported_conflict")
        return CitationDecision(
            claim_id=claim.claim_id,
            status="supported",
            reason="claim_evidence_chain_valid",
            evidence_ids=claim.evidence_ids,
        )

    @staticmethod
    def _unsupported(claim: AnswerClaim, reason: str) -> CitationDecision:
        return CitationDecision(
            claim_id=claim.claim_id,
            status="unsupported_removed",
            reason=reason,
            evidence_ids=claim.evidence_ids,
        )

    @staticmethod
    def _legacy_check(*args, **kwargs) -> CitationCheckResult:
        """Narrow compatibility until the legacy state machine is removed in Task 12."""
        fact_sheets = args[1] if len(args) > 1 else kwargs.get("fact_sheets", [])
        base_confidence = args[3] if len(args) > 3 else kwargs.get("base_confidence", 0.5)
        limitations = [] if fact_sheets else ["关键证据不足，部分结论置信度受限。"]
        return CitationCheckResult(
            confidence=(
                min(float(base_confidence), 0.45)
                if not fact_sheets
                else float(base_confidence)
            ),
            limitations=limitations,
            unsupported_or_mismatched_claims=[],
            mismatched_claims=[],
            confidence_delta=0.0,
        )


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError("evidence index values must be dict-like")


__all__ = [
    "CitationChecker",
    "CitationDecision",
    "CitationEvidence",
    "CitationReport",
]
