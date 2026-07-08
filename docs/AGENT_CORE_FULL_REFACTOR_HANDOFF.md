# Agent Core Full Refactor Handoff

> Status: execution-ready design handoff
>
> Scope: rebuild the current travel agent around a new evidence-first state-space runtime.
>
> Non-goal: preserving the old S0-S10 / S5 / S7 state-machine architecture.

## 0. Executive Summary

This document is the handoff spec for a full Agent Core refactor.

The current project should move from a sequential question-answer pipeline to a state-space driven evidence workflow:

```text
Run
  -> Topic Threads
      -> Phase States
          -> Artifact Versions
          -> Evidence Records
          -> Quality Checks
          -> Jobs
  -> Final Composition
```

The key design shift is that agent progress is no longer represented by a single mutable `TravelAgentState` and a linear `next_state`. Instead, the source of truth is a persistent store containing runs, topics, phases, artifacts, evidence, jobs, and quality checks. The root agent reads a derived projection, decides the next action, invokes a phase or control tool, and writes structured records back to the store.

The old pipeline can be mined for reusable logic, but it must not constrain the new architecture.

## 1. Design Principles Learned From ZH-video

The referenced ZH-video project is valuable because it treats agent work as a product workflow, not as a single prompt chain.

Adopt these principles:

1. State space first, flow second.
   - Do not ask only "which step are we in?"
   - Ask "which run, topic, phase, artifact version, job, and quality gate is active?"

2. Stage outputs are artifacts.
   - Every important phase writes a structured artifact.
   - Avoid hidden phase results stored only as ad hoc fields on a giant state object.

3. Artifacts are versioned.
   - Wrong or weak intermediate results should be marked `rejected`, `needs_revision`, or `superseded`, not silently overwritten.

4. Quality gates drive state transitions.
   - A phase advances only when its artifact passes the task contract.
   - Composer must not bypass quality gates by reading raw snippets directly.

5. UI and debug read projections.
   - The store is the source of truth.
   - The web UI and debug reports consume stable projections such as topic cards, adopted facts, rejected evidence, current phase, and next actions.

6. Retry locally.
   - A bad ticket price answer should retry `evidence_review` or `claim_decision`, not rerun input understanding and every tool call.

7. External actions are jobs.
   - Login attempts, browser crawling, remote APIs, slow crawlers, and paid or high-latency tools should be represented as `JobRecord`.

## 2. Current Architecture To Replace

Current main path:

```text
FastAPI
  -> TravelAgentStateMachine
      -> S0/S1 context
      -> S2 understanding
      -> S3 answer mode
      -> S4 region policy
      -> S5 evidence planning and tool use
      -> S6 evidence accumulation
      -> S7 evidence aggregation and gap loop
      -> S8 answer composition
      -> S9 citation check
      -> S10 response
```

The following modules may provide reusable logic but should not remain the new runtime source of truth:

```text
apps/agent-python/app/orchestrator/state_machine.py
apps/agent-python/app/orchestrator/states/
apps/agent-python/app/schemas/user_query.py::TravelAgentState
apps/agent-python/app/orchestrator/claude_state_runner.py
apps/agent-python/app/orchestrator/state_reducer.py
```

Reusable components to extract or adapt:

```text
apps/agent-python/app/orchestrator/answer_mode_router.py
apps/agent-python/app/orchestrator/response_contract_compiler.py
apps/agent-python/app/orchestrator/claim_search_planner.py
apps/agent-python/app/orchestrator/tool_whitelist_builder.py
apps/agent-python/app/orchestrator/evidence_policy_guard.py
apps/agent-python/app/orchestrator/evidence_scorer.py
apps/agent-python/app/orchestrator/evidence_conflict_resolver.py
apps/agent-python/app/orchestrator/citation_check.py
apps/agent-python/app/orchestrator/ticket_*.py
packages/tools/
```

Existing experimental Agent Core files can be replaced or heavily rewritten:

```text
apps/agent-python/app/orchestrator/agent_core_store.py
apps/agent-python/app/orchestrator/agent_core_supervisor.py
apps/agent-python/app/orchestrator/agent_core_pipeline_gate.py
apps/agent-python/app/orchestrator/agent_core_tool_surface.py
```

## 3. Target Runtime

### 3.1 Runtime Loop

The root agent loop must be state driven:

```text
1. Load RunProjection from Store.
2. Ask PipelineGate for visible phase tools, control tools, and blocked tools.
3. Choose exactly one next action.
4. Invoke a phase tool, control tool, utility tool, or job reconciler.
5. Validate returned records.
6. Write records to Store through reducers.
7. Emit projection update for debug/UI.
8. Repeat until delivery succeeds or a blocking condition is reached.
```

Pseudocode:

```python
while True:
    projection = store.project_run(run_id)
    if projection.status in {"succeeded", "failed", "blocked"}:
        return delivery.from_projection(projection)

    visibility = pipeline_gate.visible_tools(projection)
    action = supervisor.decide_next_action(projection, visibility)
    result = tool_surface.invoke(action, projection)

    validated = reducer.validate_records(result.records)
    store.write_records(validated)
    event_stream.publish(store.project_run(run_id))
```

The root agent should not directly compose final facts from raw evidence. It advances state and delegates phase-specific work to tools.

### 3.2 Phase Order

Use responsibility names instead of legacy S numbers:

```text
ingress
input_contract
topic_decomposition
research_plan
evidence_acquisition
evidence_review
claim_decision
answer_draft
citation_guard
delivery
```

Each topic thread may run the following topic-local phases:

```text
research_plan
evidence_acquisition
evidence_review
claim_decision
answer_draft
citation_guard
```

`ingress`, `input_contract`, `topic_decomposition`, and final `delivery` are run-level phases.

### 3.3 Phase Lifecycle

Allowed phase statuses:

```text
not_started
running
draft
pending_review
approved
needs_revision
failed
blocked
rolled_back
skipped
superseded
succeeded
```

Transition rules:

```text
not_started -> running
running -> draft
draft -> pending_review
pending_review -> approved
pending_review -> needs_revision
needs_revision -> running
running -> failed
failed -> running
approved -> succeeded
approved -> rolled_back
any active later phase -> superseded when an earlier phase is rolled back
```

Quality gates and control tools must enforce these transitions.

## 4. Data Model

Create or replace schema modules under:

```text
apps/agent-python/app/agent_core/state/
```

Recommended files:

```text
models.py
lifecycle.py
transitions.py
ids.py
```

### 4.1 RunState

```python
class RunState(BaseModel):
    run_id: str
    session_id: str | None = None
    raw_query: str
    status: Literal[
        "created", "running", "waiting", "blocked", "failed", "succeeded"
    ] = "created"
    active_topic_ids: list[str] = []
    current_phase: str | None = None
    final_artifact_id: str | None = None
    created_at: str
    updated_at: str
```

### 4.2 TopicState

```python
class TopicState(BaseModel):
    topic_id: str
    run_id: str
    task_class: str
    user_question: str
    normalized_claim: str
    status: Literal[
        "not_started", "running", "blocked", "failed", "succeeded"
    ] = "not_started"
    phase_order: list[str]
    current_phase: str | None = None
    confidence: float | None = None
    created_at: str
    updated_at: str
```

### 4.3 PhaseState

```python
class PhaseState(BaseModel):
    phase_id: str
    run_id: str
    topic_id: str | None = None
    phase_name: str
    status: str
    attempt: int = 1
    input_artifact_refs: list[str] = []
    output_artifact_refs: list[str] = []
    quality_check_ref: str | None = None
    approved_artifact_id: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str
```

### 4.4 ArtifactRecord

```python
class ArtifactRecord(BaseModel):
    artifact_id: str
    run_id: str
    topic_id: str | None = None
    phase_name: str
    artifact_type: str
    version: int
    status: Literal[
        "draft", "pending_review", "approved", "rejected",
        "needs_revision", "superseded", "succeeded"
    ]
    payload: dict[str, Any]
    evidence_refs: list[str] = []
    supersedes: str | None = None
    rejection_reasons: list[str] = []
    created_by: str
    created_at: str
```

### 4.5 EvidenceRecord

```python
class EvidenceRecord(BaseModel):
    evidence_id: str
    run_id: str
    topic_id: str | None = None
    source_name: str
    source_url: str | None = None
    source_type: str
    fetched_at: str | None = None
    claims: list[dict[str, Any]] = []
    raw_payload: dict[str, Any] = {}
    reliability: str = "unknown"
    usage_role: Literal[
        "unreviewed", "adopted", "rejected", "context", "contradiction"
    ] = "unreviewed"
```

### 4.6 QualityCheckRecord

```python
class QualityCheckRecord(BaseModel):
    check_id: str
    run_id: str
    topic_id: str | None = None
    phase_name: str
    artifact_id: str
    status: Literal["pass", "needs_revision", "fail"]
    score: float
    blocking_issues: list[str] = []
    risks: list[str] = []
    revision_instructions: list[str] = []
    created_at: str
```

### 4.7 JobRecord

```python
class JobRecord(BaseModel):
    job_id: str
    run_id: str
    topic_id: str | None = None
    phase_name: str
    tool_name: str
    status: Literal[
        "queued", "running", "succeeded", "failed", "stale", "cancelled"
    ]
    input: dict[str, Any] = {}
    output_ref: str | None = None
    error: str | None = None
    retry_count: int = 0
    retry_policy: dict[str, Any] = {}
    created_at: str
    updated_at: str
```

## 5. Store

Implement a real Store abstraction under:

```text
apps/agent-python/app/agent_core/store.py
apps/agent-python/app/agent_core/sqlite_store.py
apps/agent-python/app/agent_core/memory_store.py
```

SQLite should be the default local runtime store. Memory store is test-only.

Required tables or collections:

```text
agent_runs
agent_topics
agent_phases
agent_artifacts
agent_evidence
agent_quality_checks
agent_jobs
agent_events
```

Required store methods:

```python
create_run(...)
get_run(run_id)
create_topic(...)
list_topics(run_id)
set_phase(...)
append_artifact(...)
append_evidence(...)
append_quality_check(...)
append_job(...)
update_job(...)
approve_artifact(...)
reject_artifact(...)
rollback_to_phase(...)
project_run(run_id)
project_topic(topic_id)
```

Important rule:

```text
No phase tool may mutate phase status directly except by returning records.
Only reducers/control tools can apply state transitions.
```

## 6. Projection Model

Create:

```text
apps/agent-python/app/agent_core/projection.py
```

Projection is the read model for the supervisor, UI, debug report, and API response.

```python
class RunProjection(BaseModel):
    run_id: str
    status: str
    raw_query: str
    current_phase: str | None
    topic_cards: list[TopicCard]
    phase_cards: list[PhaseCard]
    adopted_facts: list[AdoptedFact]
    rejected_facts: list[RejectedFact]
    evidence_gaps: list[EvidenceGap]
    visible_actions: list[str]
    blocked_reasons: list[str]
    final_answer: str | None
```

The debug report should be generated from `RunProjection`, not by inspecting random runtime fields.

## 7. Topic Decomposition

The new runtime must support multi-topic questions by design.

Example:

```text
User: 都江堰门票多少钱，几点开门，适合老人去吗？
```

Expected topics:

```text
Topic 1: ticket_price_lookup
Topic 2: opening_hours_lookup
Topic 3: suitability_assessment
```

Topic decomposition output:

```python
class TopicDecompositionArtifact(BaseModel):
    topics: list[TopicDraft]
    unresolved_user_questions: list[str] = []
    requires_clarification: bool = False
```

Topic draft:

```python
class TopicDraft(BaseModel):
    task_class: str
    user_question: str
    normalized_claim: str
    target_entities: dict[str, Any]
    evidence_sensitivity: str
    priority: str
```

Each topic has an independent evidence chain. One topic may fail without blocking other topics unless the final answer cannot satisfy the user without it.

## 8. Task Contract Registry

Create:

```text
apps/agent-python/app/agent_core/contracts/
  registry.py
  base.py
  ticket_price.py
  opening_hours.py
  route.py
  nearby.py
  suitability.py
  general_lookup.py
```

Contract interface:

```python
class TaskContract(Protocol):
    task_class: str
    phase_order: list[str]

    def required_artifact_fields(self, phase_name: str) -> list[str]: ...
    def allowed_source_types(self, phase_name: str) -> list[str]: ...
    def minimum_evidence_strength(self, phase_name: str) -> str: ...
    def exclusion_rules(self, phase_name: str) -> list[str]: ...
    def quality_checks(self, phase_name: str) -> list[QualityCheck]: ...
    def answer_schema(self) -> type[BaseModel]: ...
```

Every topic must resolve to exactly one contract.

## 9. Ticket Price Contract

Ticket price lookup is the first full implementation target because it exposes the hardest current failure mode.

Required distinctions:

```text
main scenic area
internal attraction
museum or hall inside a district
boat or cruise
show or performance
guide service
combo ticket
platform package
free public street or district
```

Blocking issues:

```text
price_without_scope
free_policy_used_as_ticket_price
login_page_used_as_price_source
bundle_price_used_as_single_ticket
source_does_not_match_target_place
stale_price_without_freshness
snippet_only_for_strong_price_claim
citation_does_not_support_claim
official_background_used_as_direct_price
```

Ticket `ClaimDecisionArtifact` payload:

```python
class TicketPriceDecision(BaseModel):
    target_place: str
    target_scope: str
    adopted_prices: list[TicketPriceFact]
    free_policy: str | None = None
    rejected_candidates: list[RejectedEvidenceFact] = []
    contradictions: list[ContradictionFact] = []
    confidence: Literal["high", "medium", "low"]
    caveats: list[str] = []
```

Ticket price fact:

```python
class TicketPriceFact(BaseModel):
    product_name: str
    scope: str
    audience: str | None = None
    price: str
    currency: str = "CNY"
    date_or_validity: str | None = None
    source_refs: list[str]
```

Answer rule:

```text
If the question asks "X 门票多少钱", the answer must not collapse all related ticket products into one price.
If the target is a public district with free entrance and paid internal attractions, answer both:
1. the district/street admission policy
2. separately scoped paid attractions or products
```

## 10. Phase Tools

Create:

```text
apps/agent-python/app/agent_core/phases/
  input_contract.py
  topic_decomposition.py
  research_plan.py
  evidence_acquisition.py
  evidence_review.py
  claim_decision.py
  answer_draft.py
  citation_guard.py
  delivery.py
```

Phase tools must return records:

```python
class PhaseToolResult(BaseModel):
    artifacts: list[ArtifactRecord] = []
    evidence: list[EvidenceRecord] = []
    quality_checks: list[QualityCheckRecord] = []
    jobs: list[JobRecord] = []
    events: list[AgentEvent] = []
```

They must not directly return final user-visible free text except `delivery`.

### 10.1 Research Plan

`research_plan` produces:

```text
claim-specific search objectives
source families
tool sequence
query ladder
exclusion hints
stop conditions
```

Ticket price research plan must include:

```text
official source discovery
official ticket or booking page
OTA structured product page
local/government/public notice source only as background
query variants for target + 成人票 / 门票 / 购票 / 票价 / 优待政策
negative filters for 攻略 / 游记 / 登录 / 讲解 / 套票 when inappropriate
```

### 10.2 Evidence Acquisition

`evidence_acquisition` calls tools and writes raw evidence records.

Rules:

```text
Each tool call creates or updates a JobRecord.
Each returned fact-like item becomes EvidenceRecord.
Raw snippets remain unreviewed until evidence_review.
Search snippets cannot directly become adopted ticket prices.
```

### 10.3 Evidence Review

`evidence_review` produces:

```python
class EvidenceReviewArtifact(BaseModel):
    adopted_candidates: list[dict]
    rejected_candidates: list[dict]
    contradictions: list[dict]
    missing_fields: list[str]
    source_ranking: list[dict]
    next_gap_requests: list[dict]
```

It decides which evidence can be considered by `claim_decision`, but does not yet write the final answer.

### 10.4 Claim Decision

`claim_decision` is the fact adoption gate.

It produces a task-specific decision artifact, for example `TicketPriceDecision`.

Composer may only use approved `ClaimDecisionArtifact` records for factual claims.

### 10.5 Citation Guard

`citation_guard` checks whether every final factual sentence is supported by approved claim decisions and their evidence refs.

It must reject:

```text
claim not present in approved ClaimDecision
citation refers to source that does not support the statement
price scope mismatch
free policy presented as ticket price
bundle price presented as single ticket
```

## 11. Pipeline Gate

Create:

```text
apps/agent-python/app/agent_core/gate.py
```

The gate reads `RunProjection` and returns:

```python
class ToolVisibility(BaseModel):
    phase_name: str
    topic_id: str | None
    allowed_phase_tools: list[str]
    allowed_control_tools: list[str]
    blocked_tools: list[BlockedTool]
    required_next_actions: list[str]
    stop_reasons: list[str]
```

Gate rules:

```text
Only current phase tools are visible.
Control tools are visible when their transition preconditions are met.
External data tools are only visible in evidence_acquisition.
Composer is not visible until claim_decision is approved.
Delivery is not visible until citation_guard passes.
```

## 12. Control Tools

Create:

```text
apps/agent-python/app/agent_core/control_tools.py
```

Required tools:

```text
approve_phase(phase_id, artifact_id)
reject_artifact(artifact_id, reason)
rollback_to_phase(topic_id, phase_name, reason)
retry_phase(topic_id, phase_name, reason)
skip_phase(topic_id, phase_name, reason)
mark_phase_failed(phase_id, error)
reconcile_job(job_id)
```

Control tools must validate lifecycle transitions.

## 13. Composer Contract

Composer must become a pure artifact composer.

Allowed inputs:

```text
approved ClaimDecisionArtifact
approved EvidenceReviewArtifact summary
approved CitationGuardArtifact
run-level input contract
topic ordering and user preferences
```

Forbidden inputs:

```text
raw search snippets
unreviewed EvidenceRecord
failed or rejected artifacts
tool traces as factual evidence
model prior for evidence-required claims
```

This is the key anti-hallucination boundary.

## 14. Web and Debug Projection

Web UI should eventually show:

```text
Run status
Topic cards
Current phase per topic
Adopted facts
Rejected evidence with reasons
Evidence gaps
Retryable phases
Final answer
```

Debug session should be generated from projection:

```text
apps/agent-python/debug_last_session.md
```

Recommended sections:

```text
Run Summary
Topic Threads
Phase Timeline
Artifacts
Adopted Facts
Rejected Facts
Evidence Gaps
Jobs
Quality Checks
Final Answer
```

## 15. API Changes

Minimum API:

```text
POST /agent/query
GET  /agent/runs/{run_id}
GET  /agent/runs/{run_id}/projection
GET  /agent/runs/{run_id}/topics
GET  /agent/runs/{run_id}/artifacts
POST /agent/runs/{run_id}/retry
POST /agent/runs/{run_id}/rollback
GET  /agent/health
```

`POST /agent/query` may still return a final answer for synchronous use, but internally it should create a run and drive it through the new runtime.

## 16. Implementation Plan

### Phase A: State Core

Deliver:

```text
apps/agent-python/app/agent_core/state/models.py
apps/agent-python/app/agent_core/state/lifecycle.py
apps/agent-python/app/agent_core/store.py
apps/agent-python/app/agent_core/memory_store.py
apps/agent-python/app/agent_core/projection.py
```

Tests:

```text
create run
create topic
advance phase
append artifact version
approve artifact
rollback phase
project run
```

### Phase B: Runtime Shell

Deliver:

```text
apps/agent-python/app/agent_core/runtime.py
apps/agent-python/app/agent_core/supervisor.py
apps/agent-python/app/agent_core/gate.py
apps/agent-python/app/agent_core/tool_surface.py
apps/agent-python/app/agent_core/control_tools.py
```

Tests:

```text
single-topic happy path using fake phase tools
multi-topic happy path using fake phase tools
blocked phase when artifact quality fails
retry current phase only
```

### Phase C: Contracts

Deliver:

```text
apps/agent-python/app/agent_core/contracts/base.py
apps/agent-python/app/agent_core/contracts/registry.py
apps/agent-python/app/agent_core/contracts/ticket_price.py
apps/agent-python/app/agent_core/contracts/opening_hours.py
apps/agent-python/app/agent_core/contracts/route.py
apps/agent-python/app/agent_core/contracts/nearby.py
apps/agent-python/app/agent_core/contracts/suitability.py
```

Tests:

```text
resolve task class to contract
ticket contract rejects free-policy-as-price
ticket contract rejects login page as price
ticket contract rejects bundle price as single ticket
opening-hours contract requires open/last-entry/close distinction when available
```

### Phase D: Ticket Price End-to-End

Deliver:

```text
topic decomposition for ticket price
ticket research plan
ticket evidence acquisition adapter
ticket evidence review
ticket claim decision
ticket citation guard
ticket answer artifact
```

Tests:

```text
夫子庙门票多少钱
都江堰门票多少钱
南京夫子庙大成殿门票多少钱
免费街区 + 付费内部景点 must be separated
OTA combo ticket must not answer single attraction price
login page must be rejected as price evidence
```

### Phase E: Other Task Classes

Migrate:

```text
opening_hours_lookup
route_planning
nearby_recommendation
suitability_assessment
general_fact_lookup
comparison
itinerary
```

For each task:

```text
contract
research plan rules
evidence review artifact
claim decision artifact
quality gate
composition template
tests
```

### Phase F: API, Web, Debug

Deliver:

```text
new /agent/query runtime path
run projection endpoint
debug_last_session projection report
web topic cards
web adopted/rejected evidence display
retry/rollback controls if practical
```

### Phase G: Remove Old Runtime

Delete or archive:

```text
legacy state machine as runtime
S-number phase names in runtime
direct Composer access to raw evidence
TravelAgentState as source of truth
old S5/S7 gap loop as control path
```

Retain reusable pure functions only after moving them into the new modules.

## 17. Acceptance Criteria

The refactor is complete only when all criteria pass:

1. One user query can create multiple topic threads.
2. Each topic has independent phase states.
3. Every phase writes an artifact or an explicit skip/failure record.
4. Artifacts are versioned.
5. Evidence can be marked adopted, rejected, context, or contradiction.
6. Rejected evidence includes machine-readable reasons.
7. Composer cannot read unreviewed evidence.
8. Citation guard can fail an answer before delivery.
9. A ticket answer cannot use a free-entry public district policy as a paid ticket price.
10. A ticket answer cannot use a login page as price evidence.
11. A ticket answer cannot present bundle/package price as a single attraction ticket.
12. A single topic can be retried without rerunning the whole run.
13. One failed topic does not automatically fail other topics.
14. `debug_last_session.md` is projection-based.
15. Existing one-command startup still works.
16. Minimum tests cover ticket price, opening hours, and multi-topic decomposition.

## 18. Suggested Test Matrix

China-only examples:

```text
都江堰门票多少钱？
南京夫子庙门票多少钱？
南京夫子庙大成殿门票多少钱？
故宫今天几点闭馆？
上海迪士尼儿童票多少钱？
西湖要门票吗，雷峰塔多少钱？
从成都东站到都江堰景区怎么去？
都江堰适合带老人去吗，门票多少钱？
杭州西湖附近有什么适合老人吃饭的地方？
北京颐和园和圆明园哪个更适合带孩子？
```

Expected for ticket-like questions:

```text
public area free policy is separated from paid internal products
single ticket is separated from package and combo tickets
source scope is shown
uncertainty is explicit when source is weak
rejected evidence is visible in debug projection
```

## 19. Coding Rules For Implementing Agents

Follow these rules when executing this handoff:

1. Do not preserve the old runtime for compatibility unless temporarily needed behind a feature flag.
2. Do not add new logic to `state_machine.py` except a temporary bridge to the new runtime.
3. Do not let Composer consume raw evidence, search snippets, or tool traces.
4. Do not use `TravelAgentState` as source of truth for new code.
5. Put new runtime code under `apps/agent-python/app/agent_core/`.
6. Put task-specific contracts under `apps/agent-python/app/agent_core/contracts/`.
7. Put phase implementations under `apps/agent-python/app/agent_core/phases/`.
8. Use deterministic quality checks before LLM-assisted checks where possible.
9. Keep tool wrappers evidence-returning, but review and adoption happen inside Agent Core.
10. Add tests for every state transition and every task contract rule.

## 20. First Concrete Pull Request

Recommended first PR:

```text
Title: Introduce Agent Core state-space runtime skeleton
```

Files to add:

```text
apps/agent-python/app/agent_core/__init__.py
apps/agent-python/app/agent_core/state/__init__.py
apps/agent-python/app/agent_core/state/models.py
apps/agent-python/app/agent_core/state/lifecycle.py
apps/agent-python/app/agent_core/store.py
apps/agent-python/app/agent_core/memory_store.py
apps/agent-python/app/agent_core/projection.py
apps/agent-python/app/agent_core/control_tools.py
apps/agent-python/app/evals/agent_core_state_space_tests.py
```

First PR should not migrate all business logic. It should prove:

```text
run/topic/phase/artifact/job models exist
phase transitions are validated
artifact versions work
projection works
rollback marks later phases superseded or rolled_back
tests pass
```

After this, build the ticket price vertical slice as the second PR.

