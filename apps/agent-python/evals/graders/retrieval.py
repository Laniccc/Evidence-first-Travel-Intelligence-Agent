"""Retrieval metrics computed only from recorded ranked chunk identifiers."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field


class RetrievalCaseResult(BaseModel):
    case_id: str
    expected_chunk_ids: list[str] = Field(min_length=1)
    ranked_chunk_ids: list[str] = Field(default_factory=list)
    metadata_filter_ok: bool = True
    provenance_complete: bool = True


class RetrievalMetrics(BaseModel):
    case_count: int
    recall_at_3: float
    mrr: float
    ndcg_at_5: float
    metadata_filter_accuracy: float
    provenance_completeness: float


def grade_retrieval(results: list[RetrievalCaseResult]) -> RetrievalMetrics:
    if not results:
        return RetrievalMetrics(
            case_count=0,
            recall_at_3=0,
            mrr=0,
            ndcg_at_5=0,
            metadata_filter_accuracy=0,
            provenance_completeness=0,
        )
    recalls = []
    reciprocal_ranks = []
    ndcgs = []
    for result in results:
        expected = set(result.expected_chunk_ids)
        recalls.append(len(expected.intersection(result.ranked_chunk_ids[:3])) / len(expected))
        first_rank = next(
            (
                rank
                for rank, chunk_id in enumerate(result.ranked_chunk_ids, start=1)
                if chunk_id in expected
            ),
            None,
        )
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
        dcg = sum(
            1.0 / math.log2(rank + 1)
            for rank, chunk_id in enumerate(result.ranked_chunk_ids[:5], start=1)
            if chunk_id in expected
        )
        ideal_dcg = sum(
            1.0 / math.log2(rank + 1)
            for rank in range(1, min(len(expected), 5) + 1)
        )
        ndcgs.append(dcg / ideal_dcg if ideal_dcg else 0.0)
    count = len(results)
    return RetrievalMetrics(
        case_count=count,
        recall_at_3=sum(recalls) / count,
        mrr=sum(reciprocal_ranks) / count,
        ndcg_at_5=sum(ndcgs) / count,
        metadata_filter_accuracy=sum(item.metadata_filter_ok for item in results) / count,
        provenance_completeness=sum(item.provenance_complete for item in results) / count,
    )
