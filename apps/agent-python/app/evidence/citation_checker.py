"""Claim-level citation guard with a temporary legacy-call compatibility path."""

from __future__ import annotations

from typing import Any, Literal
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit

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
    attraction_id: str | None = None
    fact_type: str | None = None
    subtask_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    retrieved_at: datetime | None = None
    provenance_ref: str | None = None
    text_hash: str | None = None


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
        approved_decisions: list[dict] | None = None,
        as_of_by_subtask: dict | None = None,
        evaluated_at: datetime | None = None,
        **legacy_kwargs,
    ) -> CitationReport | CitationCheckResult:
        if claims is None:
            return cls._legacy_check(*legacy_args, **legacy_kwargs)

        index = {
            key: CitationEvidence.model_validate({"evidence_id": key, **_as_dict(value)})
            for key, value in (evidence_index or {}).items()
        }
        answer_claims = [AnswerClaim.model_validate(item) for item in claims]
        decisions = [cls._check_claim(claim, index, approved_decisions, as_of_by_subtask or {}, evaluated_at) for claim in answer_claims]
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
        hard_count = sum(item.status != "soft_claim_allowed" for item in decisions)
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
        approved=None, as_of=None, evaluated_at=None,
    ) -> CitationDecision:
        if not claim.hard_fact:
            if claim.claim_type != "advice" or claim.text.strip() not in {"建议预留充足时间", "建议出行前再次核对官方公告。"}:
                return cls._unsupported(claim, "unapproved_soft_claim")
            return CitationDecision(
                claim_id=claim.claim_id,
                status="soft_claim_allowed",
                reason="soft_advice_no_hard_citation_required",
                evidence_ids=claim.evidence_ids,
            )
        if not claim.evidence_ids:
            return cls._unsupported(claim, "no_evidence_ids")
        if approved is not None:
            allowed = next((d for d in approved if d.get("claim_id") == claim.claim_id), None)
            if not allowed or allowed.get("adoption") not in {"adopt", "adopt_with_limitation"} or any((
                _normalize(claim.text) != _normalize(allowed.get("adopted_value") or ""),
                claim.attraction_id != allowed.get("attraction_id"),
                claim.subtask_id != allowed.get("subtask_id"),
                claim.claim_type != allowed.get("claim_type"),
                set(claim.evidence_ids) != set(allowed.get("adopted_evidence_ids", [])),
                claim.conflict_disclosed != bool(allowed.get("conflict_evidence_ids")),
            )):
                return cls._unsupported(claim, "claim_not_approved")
        records = []
        for evidence_id in claim.evidence_ids:
            record = index.get(evidence_id)
            if record is None:
                return cls._unsupported(claim, "missing_evidence_id")
            if not record.source_url:
                return cls._unsupported(claim, "missing_source_url")
            url = urlsplit(record.source_url)
            if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
                return cls._unsupported(claim, "invalid_source_url")
            if record.version_status not in {"active", "transient"}:
                return cls._unsupported(claim, f"invalid_version_status:{record.version_status}")
            if not record.content_hash:
                return cls._unsupported(claim, "missing_content_hash")
            if record.active_content_hash and record.content_hash != record.active_content_hash:
                return cls._unsupported(claim, "hash_mismatch")
            if not record.transient and not record.document_version_id:
                return cls._unsupported(claim, "missing_version_id")
            for attr, expected, reason in (("attraction_id", claim.attraction_id, "attraction_mismatch"),
                    ("fact_type", claim.claim_type, "fact_type_mismatch"), ("subtask_id", claim.subtask_id, "subtask_mismatch")):
                actual = getattr(record, attr)
                if (approved is not None and not actual) or (actual is not None and actual != expected):
                    return cls._unsupported(claim, reason)
            if record.text_hash and record.text_hash != sha256((record.content or "").encode()).hexdigest():
                return cls._unsupported(claim, "text_hash_mismatch")
            reference_time = (as_of or {}).get(claim.subtask_id) or evaluated_at or datetime.now(UTC)
            if isinstance(reference_time, str):
                reference_time = datetime.fromisoformat(reference_time.replace("Z", "+00:00"))
            if record.transient:
                if record.content_hash != sha256((record.content or "").encode()).hexdigest():
                    return cls._unsupported(claim, "transient_hash_mismatch")
                if not all((record.retrieved_at, record.valid_to, record.provenance_ref)):
                    return cls._unsupported(claim, "transient_provenance_missing")
                reference_time = evaluated_at or datetime.now(UTC)
                if record.retrieved_at.tzinfo is None or record.retrieved_at > reference_time:
                    return cls._unsupported(claim, "source_future")
            if any(t and t.tzinfo is None for t in (record.valid_from, record.valid_to)):
                return cls._unsupported(claim, "invalid_evidence_time")
            if record.valid_to and record.valid_to <= reference_time:
                return cls._unsupported(claim, "evidence_expired")
            if record.valid_from and record.valid_from > reference_time:
                return cls._unsupported(claim, "evidence_not_yet_valid")
            records.append(record)

        distinct = {
            "".join((record.content or "").casefold().split()) for record in records
        }
        if len(distinct) > 1 and not claim.conflict_disclosed:
            return cls._unsupported(claim, "unreported_conflict")
        if _normalize(claim.text) not in {_normalize(r.content or "") for r in records}:
            return cls._unsupported(claim, "content_not_supported")
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


def _normalize(value):
    return " ".join(value.split())


__all__ = [
    "CitationChecker",
    "CitationDecision",
    "CitationEvidence",
    "CitationReport",
]
