from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.fusion import ChannelHit, reciprocal_rank_fusion
from app.evidence.retrieval.reranker import filter_candidates, filter_and_rerank
from evals import runner


def test_safety_filter_keeps_candidates_without_mutating_top_k():
    environment = runner._environment(profile="offline")
    try:
        repo, generation = environment[2], environment[6]
        chunks = [c for c in repo.list_active_chunks(runner.datetime(2026, 9, 2, tzinfo=runner.UTC))
                  if c.attraction_id == "forbidden-city"][:8]
        assert len(chunks) > 5
        plan = runner._plan({"case_id": "filter", "query_text": "故宫", "attraction_ids": ["forbidden-city"],
                             "fact_types": []}, as_of="2026-09-02T00:00:00Z")
        fused = reciprocal_rank_fusion(lexical=[ChannelHit(chunk_id=c.chunk_id, score=1) for c in chunks], dense=[])
        filtered, _ = filter_candidates(repo, plan=plan, candidates=fused, corpus_version=generation.corpus_version)
        ranked, _ = filter_and_rerank(repo, plan=plan, candidates=fused, corpus_version=generation.corpus_version)
        assert len(filtered) == len(chunks) and len(ranked) == 5
        assert RetrievalPlan.model_validate(plan.model_dump()).top_k == 5
    finally:
        environment[1].close()
        environment[0].cleanup()


def test_semantic_dataset_has_real_fixture_targets_and_unfiltered_hard_negatives():
    environment = runner._environment(profile="offline")
    try:
        rows = runner._load_jsonl(runner.ROOT / "datasets/retrieval_semantic.jsonl")
        assert len(rows) >= 8 and all(" " not in r["query_text"] for r in rows)
        assert sum(not row["fact_types"] for row in rows) >= 4
        for row in rows:
            for chunk_id in row["expected_chunk_ids"]:
                chunk = environment[2].get_chunk(chunk_id)
                assert chunk is not None and chunk.attraction_id in row["attraction_ids"]
                assert chunk.version_status.value == "active"
    finally:
        environment[1].close()
        environment[0].cleanup()
