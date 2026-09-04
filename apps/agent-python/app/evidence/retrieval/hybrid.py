"""Hybrid lexical+dense retrieval with independent failure domains."""

from __future__ import annotations

import asyncio
import re
from time import perf_counter

from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.contracts import RetrievalPlan, VectorFilters
from app.evidence.retrieval.embedding import EmbeddingProvider, EmbeddingUnavailableError
from app.evidence.retrieval.fusion import ChannelHit, reciprocal_rank_fusion
from app.evidence.retrieval.report import (
    LatencyBreakdown,
    RetrievalAttempt,
    RetrievalReport,
)
from app.evidence.retrieval.reranker import filter_and_rerank


class QdrantDenseRetriever:
    def __init__(self, repository: KnowledgeRepository, *, vector_index, embedder: EmbeddingProvider) -> None:
        self.repository = repository
        self.vector_index = vector_index
        self.embedder = embedder

    def retrieve(self, plan: RetrievalPlan, *, limit: int = 20) -> list[ChannelHit]:
        generation = self.repository.active_index_generation()
        if generation is None:
            raise RuntimeError("dense index generation is not active")
        if generation.embedding_model != self.embedder.model_name:
            raise EmbeddingUnavailableError(
                "active index generation does not match the configured embedding model"
            )
        vector = self.embedder.embed_query(plan.query_text)
        hits = self.vector_index.search(
            vector,
            filters=VectorFilters(
                attraction_ids=plan.attraction_ids,
                fact_types=[item.value for item in plan.fact_types],
                corpus_version=generation.corpus_version,
                embedding_model=generation.embedding_model,
            ),
            limit=limit,
        )
        return [
            ChannelHit(chunk_id=hit.chunk_id, score=hit.score, payload=hit.payload)
            for hit in hits
        ]


class HybridRetriever:
    CHANNEL_LIMIT = 20

    def __init__(self, *, repository: KnowledgeRepository, lexical, dense,
                 io_runner=None, channel_timeout_seconds: float = 2.0) -> None:
        self.repository = repository
        self.lexical = lexical
        self.dense = dense
        if channel_timeout_seconds <= 0:
            raise ValueError("channel timeout must be positive")
        self._io = io_runner
        self._timeout = channel_timeout_seconds

    async def aretrieve(self, plan: RetrievalPlan) -> RetrievalReport:
        if self._io is None:
            raise RuntimeError("bounded I/O runner is required for async retrieval")
        started = perf_counter()
        results = await asyncio.gather(
            self._aattempt("lexical", self.lexical, plan),
            self._aattempt("dense", self.dense, plan),
        )
        return await self._io("postfilter", self._finish, plan, started, *results)

    async def _aattempt(self, channel, retriever, plan):
        started = perf_counter()
        try:
            async with asyncio.timeout(self._timeout):
                if hasattr(retriever, "aretrieve"):
                    hits = await retriever.aretrieve(plan, limit=self.CHANNEL_LIMIT)
                else:
                    hits = await self._io(channel, retriever.retrieve, plan, limit=self.CHANNEL_LIMIT)
        except Exception as exc:
            return [], RetrievalAttempt(channel=channel, status="failed",
                latency_ms=_elapsed_ms(started), failure_code=_failure_code(exc))
        return hits, RetrievalAttempt(channel=channel, status="success" if hits else "empty",
                                     result_count=len(hits), latency_ms=_elapsed_ms(started))

    def retrieve(self, plan: RetrievalPlan) -> RetrievalReport:
        started = perf_counter()
        lexical_hits, lexical_attempt = self._attempt("lexical", self.lexical, plan)
        dense_hits, dense_attempt = self._attempt("dense", self.dense, plan)
        return self._finish(plan, started, (lexical_hits, lexical_attempt), (dense_hits, dense_attempt))

    def _finish(self, plan, started, lexical_result, dense_result):
        lexical_hits, lexical_attempt = lexical_result
        dense_hits, dense_attempt = dense_result
        fusion_started = perf_counter()
        fused = reciprocal_rank_fusion(
            lexical=lexical_hits,
            dense=dense_hits,
            rrf_k=60,
            candidate_limit=8,
        )
        fusion_ms = _elapsed_ms(fusion_started)

        active_generation = self.repository.active_index_generation()
        corpus_version = active_generation.corpus_version if active_generation else "unindexed"
        rerank_started = perf_counter()
        final_hits, rejections = filter_and_rerank(
            self.repository,
            plan=plan,
            candidates=fused,
            corpus_version=corpus_version,
        )
        rerank_ms = _elapsed_ms(rerank_started)
        degradation = self._degradation(lexical_attempt, dense_attempt, final_hits)
        coverage_hints = [] if final_hits else ["no_active_evidence"]
        return RetrievalReport(
            subtask_id=plan.subtask_id,
            retrieval_plan=plan,
            corpus_version=corpus_version,
            index_generation=active_generation.generation_id if active_generation else None,
            embedding_model=active_generation.embedding_model if active_generation else None,
            lexical_attempt=lexical_attempt,
            dense_attempt=dense_attempt,
            fusion_candidates=fused,
            post_filter_rejections=rejections,
            final_hits=final_hits,
            coverage_hints=coverage_hints,
            degradation=degradation,
            latency_breakdown=LatencyBreakdown(
                lexical_ms=lexical_attempt.latency_ms,
                dense_ms=dense_attempt.latency_ms,
                fusion_ms=fusion_ms,
                post_filter_rerank_ms=rerank_ms,
                total_ms=_elapsed_ms(started),
            ),
        )

    def _attempt(self, channel: str, retriever, plan: RetrievalPlan):
        started = perf_counter()
        try:
            hits = retriever.retrieve(plan, limit=self.CHANNEL_LIMIT)
        except Exception as exc:
            return [], RetrievalAttempt(
                channel=channel,
                status="failed",
                latency_ms=_elapsed_ms(started),
                failure_code=_failure_code(exc),
            )
        return hits, RetrievalAttempt(
            channel=channel,
            status="success" if hits else "empty",
            result_count=len(hits),
            latency_ms=_elapsed_ms(started),
        )

    @staticmethod
    def _degradation(lexical, dense, final_hits):
        if lexical.status == "failed" and dense.status == "failed":
            return "all_failed"
        if dense.status == "failed":
            return "lexical_only"
        if lexical.status == "failed":
            return "dense_only"
        if not final_hits:
            return "no_results"
        return "none"


def _elapsed_ms(started: float) -> float:
    return max(0.0, (perf_counter() - started) * 1000)


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, EmbeddingUnavailableError):
        return "embedding_unavailable"
    name = type(exc).__name__.removesuffix("Error")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower() or "retrieval_failure"
