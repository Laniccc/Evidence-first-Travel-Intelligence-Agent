# Agent Core Current Status

Last updated: 2026-06-30

## Runtime Mainline

`POST /agent/query` now enters the new state-space runtime:

```text
apps/agent-python/app/main.py
  -> app.agent_core.runtime.AgentCoreRuntime
  -> AgentCoreSupervisor
  -> agent_core/phases/*
  -> agent_core/contracts/*
  -> MemoryAgentStore
  -> RunProjection
```

The legacy `app/orchestrator/state_machine.py` path remains in the repository
as migration/reference code, but it is not the primary FastAPI `/agent/query`
runtime after this change.

## Implemented In This Cut

- Run / Topic / Phase / Artifact / Evidence / QualityCheck / Job state-space models.
- Memory and SQLite store skeletons.
- Projection endpoints:
  - `GET /agent/runs/{run_id}/projection`
  - `GET /agent/runs/{run_id}/topics`
  - `GET /agent/runs/{run_id}/artifacts`
- Deterministic `AgentCoreRuntime`.
- Deterministic `AgentCoreSupervisor`.
- Phase tool facade and phase modules:
  - ingress
  - input_contract
  - topic_decomposition
  - research_plan
  - evidence_acquisition
  - evidence_review
  - claim_decision
  - answer_draft
  - citation_guard
  - delivery
- Task contract registry with first implementations for:
  - ticket_price_lookup
  - opening_hours_lookup
  - route_planning
  - nearby_recommendation
  - suitability_assessment
  - general_lookup

## Important Behavior

The first new runtime cut is deliberately conservative. It does not pretend to
have live ticket prices when real providers are not connected to the new
`evidence_acquisition` phase.

For ticket-price questions, the contract explicitly prevents these failures:

- free public-area policy treated as paid ticket price
- login page treated as price evidence
- bundle/combo/package price treated as single-attraction ticket
- guide/boat/show price treated as general admission without explicit scope

When evidence is insufficient, the answer should say so instead of inventing a
price.

## Verified Tests

The current Agent Core verification set passes:

```text
python -m pytest \
  apps/agent-python/app/evals/agent_core_state_space_tests.py \
  apps/agent-python/app/evals/test_pipeline_api.py \
  apps/agent-python/app/evals/test_ticket_price_contract.py \
  apps/agent-python/app/evals/test_provider_contract.py \
  apps/agent-python/app/evals/agent_core_store_tests.py \
  apps/agent-python/app/evals/agent_core_prompt_guidance_tests.py -q
```

Current result:

```text
163 passed, 2 skipped
```

## Known Gaps

- `evidence_acquisition` is still a local deterministic seed phase; real MCP,
  browser, ticket, map, and review providers must be wired into this phase next.
- SQLite store exists but the default runtime currently uses `MemoryAgentStore`.
- Legacy S5/S7 tests still exist and many full-suite evals target the old
  behavior.
- Several legacy docs still describe the old state machine path and should be
  cleaned after the new runtime stabilizes.
- Some existing files contain mojibake text; avoid broad doc rewrites until
  encoding is normalized.

## Next Work

1. Move real tool/provider calls behind `agent_core/phases/evidence_acquisition.py`.
2. Persist runtime runs through `SQLiteAgentStore`.
3. Extend task contracts from skeleton to complete deterministic gates.
4. Move debug report generation fully onto `RunProjection`.
5. Retire or rewrite legacy evals that assert old S5/S7 internals.

