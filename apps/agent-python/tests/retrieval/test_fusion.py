from app.evidence.retrieval.fusion import ChannelHit, reciprocal_rank_fusion


def hit(chunk_id: str) -> ChannelHit:
    return ChannelHit(chunk_id=chunk_id, score=1.0, payload={"chunk_id": chunk_id})


def test_rrf_rewards_candidates_found_by_both_channels():
    fused = reciprocal_rank_fusion(
        lexical=[hit("a"), hit("b")],
        dense=[hit("b"), hit("c")],
        rrf_k=60,
    )

    assert fused[0].chunk_id == "b"
    assert fused[0].channels == ["lexical", "dense"]


def test_rrf_has_deterministic_tie_breaking_and_candidate_limit():
    fused = reciprocal_rank_fusion(
        lexical=[hit("b"), hit("a"), hit("c")],
        dense=[],
        candidate_limit=2,
    )

    assert [candidate.chunk_id for candidate in fused] == ["b", "a"]
