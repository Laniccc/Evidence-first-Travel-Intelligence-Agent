# CI Compatibility and Bounded Composer Implementation Plan

> Execution: existing dedicated worktree, sequential local execution. User authorized implementation, push and main merge.

**Goal:** Restore green Actions, add a minimal constrained LLM Composer with deterministic fallback, and deliver to main.

**Architecture:** Keep the tested Anthropic/httpx pair pinned. Online Composer proposes only an ordering of the complete approved Claim IDs. Code reconstructs immutable claims and citations; Citation Guard remains the delivery gate. One model call, bounded input/output and timeout, no repair loop. Missing model, timeout, transport failure or invalid selection retains the full evidence template.

**Tech Stack:** Existing Python/Pydantic/Anthropic, SQLite audits, pytest and GitHub Actions.

## Task 1: CI compatibility

- Confirm failed run logs (33944951517: 10 failures from httpx/httpx2 type mismatch).
- Modify apps/agent-python/requirements.txt: anthropic==0.104.1 and httpx==0.28.1, the pair used in the 298-test local baseline.
- Commit/push the isolated fix and check all four Actions jobs. Preserve real SDK mock transport tests and all release thresholds.

## Task 2: Composer

- Create apps/agent-python/app/composition/llm_composer.py and tests/states/test_llm_composer.py.
- Red tests: valid reordered IDs preserve exact claims, unknown/duplicate/missing IDs and extra text rejected, oversized input bypasses model; state timeout/transport/invalid output falls back once, cancellation propagates.
- Update orchestration/states/answer_composition.py, state_machine.py, main.py and config.py: production injection with one-call timeout below state deadline, typed audit failure code and recovery; no changes to public Java/Web DTO.
- Update integration/test_online_runtime_wiring.py and evals/closure_runtime.py fixtures to return Composer ID plans. Verify real factory path and final Citation Guard, not only isolated adapter.
- Update live smoke call counts/checks and architecture/runtime documentation.

## Task 3: Verify and deliver

- Run Python full pytest and all offline Eval with fail-on-regression; unchanged 112 cases and 21 gates must pass. Report generated artifacts under evals/reports/generated.
- Push feature branch, inspect Actions until four jobs are green. Inspect main working tree and remote tip; preserve the user's untracked image.
- Fast-forward main if possible, otherwise inspect changes and perform a normal reviewed merge. Push main and verify its exact commit's Actions.
- Record actual results and commit IDs; no real provider calls are needed for this change.
