# Minimal LangGraph Scheduling Migration

**Goal:** Make LangGraph StateGraph the default workflow scheduler while preserving typed StateHandler business behavior, API contracts and SQLite artifact replay.

**Architecture:** A thin graph state holds the original StateContext reference as run_context (the name context is already a business node), plus next/terminal/failure/step routing metadata. Every nonterminal AgentState has its own node. Conditional edges derive from ALLOWED_TRANSITIONS; terminal routes map to END. Handler execution timeout/retry/audit is extracted unchanged and shared with legacy.

**Scope:** Python orchestration only. No Handler, RAG, MCP, Evidence, Promotion, Composer, Citation or external schema redesign. No benchmark runs, score changes, new checkpointer, tracing service, remote graph or model-selected routes.

## Steps

1. Read the state runtime/contracts/transition table, all production handlers and factory, persistence/replay and related tests. Pin the locally available stable langgraph 1.2.7; preserve anthropic 0.104.1/httpx 0.28.1.
2. Add tests/orchestration/test_langgraph_workflow.py: actual compile/nodes/edges, real Handler routing, gap/safe/terminal paths, object identity, illegal route refusal, bounded execution and audit parity against legacy. Reuse existing API, promotion and replay regression tests.
3. Extract execute_state_handler into app/orchestration/state_execution.py. Legacy _run_handler delegates to it; its top-level loop remains available.
4. Add app/orchestration/langgraph_runtime.py: compile registered business nodes, call shared execution helper, preserve transition validation/artifact commit/audit order and explicit step limit, route to END on terminal outcomes. No internal workflow while-loop or LangGraph retry policy.
5. Add ORCHESTRATION_ENGINE=langgraph|legacy (default langgraph) in config.py/.env.example; select runtime in state_machine.py and pass configuration from main.py. Keep the public entrypoint and response projection unchanged.
6. Run focused orchestration/state/API/persistence/promotion/replay tests. Optional broader pytest excludes eval runner tests that generate benchmark scores; do not run Recruitment Benchmark, evals.runner or real providers for this migration. The user's explicit no-rebenchmark instruction overrides the general release-gate command for this task only; thresholds/data remain untouched.
7. Update README, RUNBOOK and STATE_CHAIN with actual default runtime, mapping, fallback and scope. Record test commands/results without updating historical benchmark numbers.

## References

- Official Graph API: https://docs.langchain.com/oss/python/langgraph/graph-api
- Version and API signatures verified against installed langgraph 1.2.7; no upgrade to existing validated SDK/transport packages.

## Verification note

The first broad regression run (excluding tests/evals) had 306 passed, 1 skipped and one unrelated fixed-date fixture failure. tests/retrieval/test_natural_queries.py published a version valid until 2026-09-07 using today's wall clock; its intended clock is NOW=2026-09-04. Inject the repository's existing clock=lambda: NOW in that test only. No production time policy, fixture fact, expected assertion, benchmark dataset or score changed.

## Final local acceptance

- Branch: codex/langgraph-scheduling, based on b1826c7.
- python -m pytest tests/retrieval/test_natural_queries.py tests/orchestration/test_langgraph_workflow.py -q: 25 passed (20 graph-specific cases plus 5 existing retrieval tests).
- python -m pytest -q --ignore=tests/evals: 307 passed / 1 skipped / 1 warning. Skipped: opt-in Qdrant server; warning: existing Starlette/httpx deprecation.
- pip install --dry-run -r requirements.txt: all requirements already satisfied; no dependency upgrades/install mutations.
- AST comparison confirms the shared executor body is identical to the old _run_handler except replacing self.audit with the audit argument.
- Graph smoke covers real fact/suitability/comparison Handlers through Citation Guard to delivery, RAG miss/gap, clarification/safe failure, real factory promotion path with fake external transports, legacy option, terminal entry, missing handler, illegal edge, retry/recovery, cancellation and legal cycle step budget.
- Existing API, terminal failure, SQLite persistence, MCP, promotion, composer, citation and Replay tests run under default LangGraph as part of the broad regression. No Java/Web contract changed.
- No Recruitment Benchmark, evals.runner, live provider request, new metrics report or historical score update. Existing evals/benchmarks, docs/benchmarks and the personal PNG are untouched.

## Exact file inventory

New:

- apps/agent-python/app/orchestration/langgraph_runtime.py
- apps/agent-python/app/orchestration/state_execution.py
- apps/agent-python/tests/orchestration/test_langgraph_workflow.py
- docs/plans/2026-09-08-langgraph-scheduling.md

Modified:

- apps/agent-python/app/orchestration/state_machine.py — engine selection; all Handler construction and terminal projection retained.
- apps/agent-python/app/orchestration/state_runtime.py — legacy loop retained; _run_handler delegates to the extracted helper.
- apps/agent-python/app/config.py — typed engine option, default langgraph.
- apps/agent-python/app/main.py — forwards the engine setting.
- apps/agent-python/requirements.txt — adds only langgraph==1.2.7.
- apps/agent-python/.env.example — documents the default.
- apps/agent-python/tests/retrieval/test_natural_queries.py — one-line deterministic clock injection.
- README.md, RUNBOOK.md, docs/architecture/STATE_CHAIN.md — current architecture and rollback instructions.

StateContext remains the authoritative object held as run_context; the carrier adds only routing and step metadata. Existing handlers execute once per graph visit through the shared policy helper, which retains bounded retries. ALLOWED_TRANSITIONS creates conditional edge maps and is checked again before artifact commit. Terminals map to END and use the existing response builder. The old runtime and tests remain available. No business capability was removed, and no intended business behavior changed.
