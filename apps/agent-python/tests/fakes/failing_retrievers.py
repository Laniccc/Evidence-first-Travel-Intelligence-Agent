from datetime import UTC, datetime

from app.evidence.knowledge.models import FactType
from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.report import (
    LatencyBreakdown,
    PostFilterRejection,
    RetrievalAttempt,
    RetrievalReport,
    RetrievedChunk,
)


def plan(
    *,
    subtask_id: str = "sub-1",
    attraction_id: str = "forbidden-city",
    fact_types: list[FactType] | None = None,
    task_type: str = "fact_query",
) -> RetrievalPlan:
    return RetrievalPlan(
        task_type=task_type,
        query_text="故宫开放时间",
        attraction_ids=[attraction_id],
        fact_types=fact_types or [FactType.OPENING_HOURS],
        as_of=datetime(2026, 9, 2, tzinfo=UTC),
        top_k=3,
        subtask_id=subtask_id,
    )


def chunk(
    chunk_id: str,
    content: str,
    *,
    fact_type: str = "opening_hours",
    attraction_id: str = "forbidden-city",
    authority: float = 1.0,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_version_id=f"version-{chunk_id}",
        attraction_id=attraction_id,
        fact_type=fact_type,
        content=content,
        source_id=f"source-{chunk_id}",
        source_url=f"https://example.test/{chunk_id}",
        source_title=f"source {chunk_id}",
        source_authority=authority,
        content_hash=f"hash-{chunk_id}",
        retrieval_channels=["lexical"],
        rrf_score=0.1,
        final_score=authority,
        corpus_version="corpus-1",
    )


def report(
    retrieval_plan: RetrievalPlan | None = None,
    *,
    hits: list[RetrievedChunk] | None = None,
    degradation: str = "none",
    dense_failure: str | None = None,
    lexical_failure: str | None = None,
    rejections: list[PostFilterRejection] | None = None,
) -> RetrievalReport:
    retrieval_plan = retrieval_plan or plan()
    hits = list(hits or [])
    return RetrievalReport(
        subtask_id=retrieval_plan.subtask_id,
        retrieval_plan=retrieval_plan,
        corpus_version="corpus-1",
        index_generation="generation-1",
        embedding_model="fake-v1",
        lexical_attempt=RetrievalAttempt(
            channel="lexical",
            status="failed" if lexical_failure else ("success" if hits else "empty"),
            result_count=0 if lexical_failure else len(hits),
            latency_ms=1,
            failure_code=lexical_failure,
        ),
        dense_attempt=RetrievalAttempt(
            channel="dense",
            status="failed" if dense_failure else ("success" if hits else "empty"),
            result_count=0 if dense_failure else len(hits),
            latency_ms=1,
            failure_code=dense_failure,
        ),
        post_filter_rejections=rejections or [],
        final_hits=hits,
        degradation=degradation,
        latency_breakdown=LatencyBreakdown(
            lexical_ms=1,
            dense_ms=1,
            fusion_ms=0,
            post_filter_rerank_ms=0,
            total_ms=2,
        ),
    )


class StaticRetriever:
    def __init__(self, reports):
        self._reports = list(reports)

    def retrieve(self, retrieval_plan):
        return self._reports.pop(0)


def lexical_success_dense_timeout():
    return StaticRetriever(
        [
            report(
                hits=[chunk("fc-hours", "故宫八点三十分开放")],
                degradation="lexical_only",
                dense_failure="timeout",
            )
        ]
    )
