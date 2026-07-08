# Agent Core Loop Repair Analysis

Date: 2026-07-01

## Diagnosis

The latest run shows that the ticket-price contract became safer, but the
Agent Core loop is still architecturally incomplete.

Observed state:

- `claim_decision: needs_revision`
- `answer_draft: succeeded`
- `citation_guard: succeeded`
- `delivery: succeeded`
- `adopted_facts: []`
- `evidence_gaps: []`

This means phase state is recorded, but it does not govern execution. The
supervisor is still effectively a sequential phase runner:

```text
for phase in TOPIC_PHASE_ORDER:
    run phase
```

The architecture we want is state-driven:

```text
Store Projection -> Pipeline Gate -> Supervisor Policy -> Tool Surface /
Control Tool -> Store Records -> Projection refresh
```

## Architectural Problems

1. Pipeline Gate is advisory, not a hard boundary.
2. Phase success and business answerability are conflated.
3. `needs_revision` does not create a first-class evidence gap.
4. Topic/run statuses are marked as ordinary success even when a topic has no
   approved claim decision.
5. Delivery has only one mode, so limited safe failure is indistinguishable
   from a fully answered result.

## Repair Objective

Make Agent Core a state-driven loop:

- A topic may only advance to `answer_draft` when `claim_decision` is approved.
- A topic with `needs_revision` must produce an `EvidenceGap` projection.
- If the gap is not retried/resolved in this minimal implementation, the topic
  and run must finish as `succeeded_limited`, not ordinary `succeeded`.
- Delivery must distinguish `normal` from `limited` delivery.
- The projection must expose the reason a run could not produce a fully
  answerable result.

This repair intentionally avoids ticket-specific branching in the supervisor.
Ticket price is only one contract that can produce a failed quality check; the
loop behavior must apply to all task classes.

## Follow-up Repair: Gap-driven Retry Loop

The first repair made `needs_revision` visible, but still treated the evidence
gap mostly as a delivery signal. That is not enough for the target Agent Core
architecture: a gap must become control data for the supervisor.

Additional diagnosis:

- A phase-level `needs_revision` should not immediately end the topic if the
  gap still has retry budget.
- Retried evidence acquisition needs the missing-evidence description and
  revision instructions in the tool payload, otherwise the second query repeats
  the first query too closely.
- Projection must prefer first-class `evidence_gap` artifacts over fallback
  phase-derived gaps, or a resolved/exhausted gap can be displayed as `open`.
- When a retry succeeds and `claim_decision` passes, the gap needs an explicit
  `resolved` state so debug output does not show stale unresolved work.

Implemented state chain:

```text
claim_decision:needs_revision
  -> evidence_gap:open
  -> supervisor_policy:retry_gap (while retry_count < max_retries)
  -> rollback_to_phase(evidence_acquisition)
  -> evidence_acquisition receives gap_retry payload
  -> claim_decision
     -> evidence_gap:resolved when claims pass
     -> evidence_gap:exhausted + succeeded_limited when retry budget is spent
```

This keeps the fix architecture-level rather than ticket-specific: ticket price
is one source of evidence gaps, but the same loop can be reused by opening
hours, route, nearby, and suitability tasks whenever their phase contracts
produce a first-class gap.
