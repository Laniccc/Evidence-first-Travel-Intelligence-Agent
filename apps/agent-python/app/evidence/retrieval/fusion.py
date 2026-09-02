"""Channel-neutral reciprocal rank fusion."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChannelHit(BaseModel):
    chunk_id: str
    score: float
    payload: dict = Field(default_factory=dict)
    document_version_id: str | None = None
    content_hash: str | None = None


class FusionCandidate(BaseModel):
    chunk_id: str
    rrf_score: float
    channels: list[str]
    lexical_rank: int | None = None
    dense_rank: int | None = None
    payload_by_channel: dict[str, dict] = Field(default_factory=dict)


def reciprocal_rank_fusion(
    *,
    lexical: list[ChannelHit],
    dense: list[ChannelHit],
    rrf_k: int = 60,
    candidate_limit: int = 8,
) -> list[FusionCandidate]:
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")

    values: dict[str, dict] = {}
    for channel, hits in (("lexical", lexical), ("dense", dense)):
        for rank, hit in enumerate(hits, start=1):
            item = values.setdefault(
                hit.chunk_id,
                {
                    "score": 0.0,
                    "channels": [],
                    "lexical_rank": None,
                    "dense_rank": None,
                    "payloads": {},
                    "first_seen": len(values),
                },
            )
            item["score"] += 1.0 / (rrf_k + rank)
            item["channels"].append(channel)
            item[f"{channel}_rank"] = rank
            item["payloads"][channel] = dict(hit.payload)

    ordered = sorted(
        values.items(),
        key=lambda pair: (-pair[1]["score"], pair[1]["first_seen"], pair[0]),
    )[:candidate_limit]
    return [
        FusionCandidate(
            chunk_id=chunk_id,
            rrf_score=item["score"],
            channels=item["channels"],
            lexical_rank=item["lexical_rank"],
            dense_rank=item["dense_rank"],
            payload_by_channel=item["payloads"],
        )
        for chunk_id, item in ordered
    ]
