# S7 / S8 Pipeline

Evidence-first travel agent stages **S7** (evidence curation) and **S8** (answer composition) after S5 tool/evidence gathering.

## Flow

```
S2/S3 → UserNeedResidual (needs only, no user-stated facts)
S5    → evidence[]
S7    → EvidenceBrief (LLM curation loop)
S8    → FinalAnswerDraft (LLM only)
```

## S2 User Need Residual

`build_user_need_residual()` / `attach_user_need_residual()` produce a **read-only** payload for S7/S8:

| Included | Excluded |
|----------|----------|
| intent_summary, task_family, decision_type | raw_user_query |
| information_needs, user_constraints | entities / places / city |
| answer_policy, key_concerns, missing_slots | rewritten_query, assumptions |
| claim_requirements (types + priority) | evidence, tool traces |

Prompt rule: residual describes *what to answer*, not verified destination facts.

## S7 Evidence Aggregation

State: `evidence_aggregation` (`EVIDENCE_AGGREGATION_POLICY`, max 4 steps).

Sub-agents (controlled loop via `ClaudeStateRunner`):

1. `evidence_curation_planner_agent` — plan from `user_need_residual` + evidence index
2. `claim_relevance_filter_agent` — relevance filter; drops `is_search_miss_value` claims
3. `evidence_conflict_analyzer_agent` — conflicts + `conflict_notes`

Output: `EvidenceBrief` → `state.evidence_brief` and `state.field_evidence_summary` (API compatible).

**Deprecated on main path:** `EvidenceAggregator`, `ReviewAspectMiningAgent`, `TravelSuitabilityScorer` (kept for legacy unit tests only).

## S8 Answer Composition

`AnswerComposerAgent` is **LLM-only**:

- Input bundle: `user_need_residual`, `evidence_brief`, `coverage_report`, `overall_confidence`
- If `overall_confidence < 0.55` or required claims uncovered → prompt requires prominent 证据不足/未核实
- JSON parse failure → one retry; total failure → infrastructure error draft (no static templates)

`compose_mode` (`fact_lookup`, `suitability`, `compare`, `crowd`, `itinerary`, `advisory`) affects **prompt sections only**, not static fallbacks.

## State machine paths

All compose paths call `_run_evidence_curation()` before `_run_answer_composition()`:

- `_run_single`, `_run_advisory`, `_run_crowd_inquiry`, `_run_compare`, `_run_itinerary`

`compose_mode` resolved via `_resolve_compose_mode(state)` on every path.

## Quick verification

```bash
cd apps/agent-python
python -m compileall app
pytest app/evals/evidence_curation_tests.py app/evals/user_need_residual_tests.py app/evals/composer_compose_tests.py -q
```
