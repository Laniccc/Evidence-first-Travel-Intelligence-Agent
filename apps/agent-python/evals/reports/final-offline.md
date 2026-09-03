# Final offline evaluation

- Result: **PASS**
- Cases: 71
- Corpus: `portfolio-2026-09-02`
- Limitation: deterministic feature hashing validates control flow and ranking mechanics, not real semantic embedding quality.

## Release gates

| Metric | Actual | Gate | Result |
|---|---:|---:|---|
| recall_at_3 | 1.0000 | >= 0.90 | PASS |
| mrr | 1.0000 | >= 0.85 | PASS |
| ndcg_at_5 | 1.0000 | >= 0.90 | PASS |
| metadata_filter_accuracy | 1.0000 | == 1.00 | PASS |
| non_active_leakage_rate | 0.0000 | == 0.00 | PASS |
| state_path_accuracy | 1.0000 | >= 0.95 | PASS |
| illegal_transitions | 0.0000 | == 0.00 | PASS |
| stale_vector_rejection | 1.0000 | == 1.00 | PASS |
| index_rebuild_consistency | 1.0000 | == 1.00 | PASS |
| unsupported_hard_facts | 0.0000 | == 0.00 | PASS |
| citation_precision | 1.0000 | >= 0.95 | PASS |
| abstention_precision | 1.0000 | >= 0.90 | PASS |
| replay_consistency | 1.0000 | == 1.00 | PASS |

## Retrieval ablations

| Mode | Recall@3 | MRR | nDCG@5 | Metadata | Provenance |
|---|---:|---:|---:|---:|---:|
| lexical-only | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dense-only | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| hybrid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| hybrid+rerank | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

`hybrid` applies RRF plus mandatory version/hash filters; `hybrid+rerank` additionally orders by authority and freshness. Equal scores on this controlled corpus are not evidence of semantic lift.

## Bad cases

None in this deterministic regression set.
