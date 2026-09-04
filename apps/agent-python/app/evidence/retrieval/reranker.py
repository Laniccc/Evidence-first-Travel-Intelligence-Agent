"""Authoritative post-filter and deterministic evidence reranking."""

from __future__ import annotations

from datetime import UTC, datetime

from app.evidence.knowledge.models import VersionStatus
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.fusion import FusionCandidate
from app.evidence.retrieval.report import PostFilterRejection, RetrievedChunk


def filter_and_rerank(
    repository: KnowledgeRepository,
    *,
    plan: RetrievalPlan,
    candidates: list[FusionCandidate],
    corpus_version: str,
) -> tuple[list[RetrievedChunk], list[PostFilterRejection]]:
    accepted, rejected = filter_candidates(repository, plan=plan, candidates=candidates,
                                           corpus_version=corpus_version)
    accepted.sort(key=lambda item: (-item.final_score, item.chunk_id))
    return accepted[: plan.top_k], rejected


def filter_candidates(
    repository: KnowledgeRepository,
    *,
    plan: RetrievalPlan,
    candidates: list[FusionCandidate],
    corpus_version: str,
) -> tuple[list[RetrievedChunk], list[PostFilterRejection]]:
    accepted = []
    rejected: list[PostFilterRejection] = []
    maximum_rrf = max((candidate.rrf_score for candidate in candidates), default=1.0)
    expected_fact_types = {item.value for item in plan.fact_types}

    for candidate in candidates:
        chunk = repository.get_chunk(candidate.chunk_id)
        if chunk is None or chunk.attraction_id not in plan.attraction_ids:
            rejected.append(PostFilterRejection(chunk_id=candidate.chunk_id, reason="missing_chunk"))
            continue
        if expected_fact_types and chunk.fact_type.value not in expected_fact_types:
            rejected.append(PostFilterRejection(chunk_id=candidate.chunk_id, reason="missing_chunk"))
            continue
        status_reason = _status_rejection(chunk.version_status, chunk.valid_from, chunk.valid_to, plan.as_of)
        if status_reason:
            rejected.append(PostFilterRejection(chunk_id=candidate.chunk_id, reason=status_reason))
            continue
        if plan.require_explicit_temporal_coverage and (chunk.valid_from is None or chunk.valid_to is None):
            rejected.append(PostFilterRejection(chunk_id=candidate.chunk_id, reason="temporal_coverage_missing"))
            continue

        channels = list(candidate.channels)
        dense_payload = candidate.payload_by_channel.get("dense")
        if dense_payload and (
            dense_payload.get("content_hash") != chunk.content_hash
            or dense_payload.get("document_version_id") != chunk.document_version_id
        ):
            rejected.append(
                PostFilterRejection(
                    chunk_id=candidate.chunk_id,
                    reason="hash_mismatch",
                    channel="dense",
                )
            )
            if "lexical" not in channels:
                continue
            channels = ["lexical"]

        normalized_rrf = candidate.rrf_score / maximum_rrf if maximum_rrf else 0.0
        freshness = _freshness_score(chunk.published_at, plan.as_of)
        fact_match = 1.0 if not expected_fact_types or chunk.fact_type.value in expected_fact_types else 0.0
        final_score = (
            0.60 * normalized_rrf
            + 0.20 * chunk.source_authority
            + 0.15 * freshness
            + 0.05 * fact_match
        )
        accepted.append(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_version_id=chunk.document_version_id,
                attraction_id=chunk.attraction_id,
                fact_type=chunk.fact_type.value,
                content=chunk.content,
                source_id=chunk.source_id,
                source_url=chunk.source_url,
                source_title=chunk.source_title,
                source_authority=chunk.source_authority,
                content_hash=chunk.content_hash,
                locator=chunk.locator,
                valid_from=chunk.valid_from.isoformat() if chunk.valid_from else None,
                valid_to=chunk.valid_to.isoformat() if chunk.valid_to else None,
                retrieval_channels=channels,
                rrf_score=candidate.rrf_score,
                final_score=final_score,
                corpus_version=corpus_version,
            )
        )
    # Safety filtering must not truncate or choose an ablation's ranking policy.
    return accepted, rejected


def _status_rejection(status, valid_from, valid_to, as_of):
    if status is VersionStatus.SUPERSEDED:
        return "superseded_version"
    if status is VersionStatus.EXPIRED or (valid_to is not None and valid_to <= as_of):
        return "expired_version"
    if status is not VersionStatus.ACTIVE or (valid_from is not None and valid_from > as_of):
        return "pending_version"
    return None


def _freshness_score(published_at: datetime | None, as_of: datetime) -> float:
    if published_at is None:
        return 0.5
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    age_days = max(0, (as_of - published_at).days)
    if age_days <= 30:
        return 1.0
    if age_days <= 90:
        return 0.75
    if age_days <= 365:
        return 0.5
    return 0.25
