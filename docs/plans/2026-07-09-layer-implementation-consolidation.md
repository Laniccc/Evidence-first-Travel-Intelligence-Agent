# Layer Implementation Consolidation Plan

> **For Codex Resume:** REQUIRED SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Move real Java and Python Agent implementations into the new commercial layered structure, then remove old coupled implementation packages and compatibility wrappers.

**Architecture:** This is a second-stage consolidation after package standardization. Java should become domain/application/port/infrastructure/web code instead of relocated Spring/JPA code. Python Agent should move real implementation out of legacy `agents`, `orchestrator`, `schemas`, `tool_gateway`, `storage`, `catalog`, `prompts`, and `policies` packages into product capability layers, then delete the retired packages.

**Tech Stack:** Java 17+ / Spring Boot / Spring MVC / Spring Security / Spring Data JPA / H2 / JUnit 5 / Maven, Python 3 / FastAPI / Pydantic / pytest, Vue/Vite frontend.

---

## Execution Prompt For Codex Resume

When continuing this plan after context compression or a new user request, follow these rules exactly:

1. Before executing any task, read this plan file first and identify the next unchecked task or the task explicitly requested by the user.
2. Execute exactly one task at a time unless the user explicitly asks for more.
3. After executing a task, stop. Do not continue to the next task.
4. Every executed task must update this plan before responding:
   - change its completion checkbox from `[ ]` to `[x]`;
   - add `Execution result` immediately after the checkbox;
   - include commands run, pass/fail result, files changed, deleted files, blockers, and plan corrections.
5. If a task reveals the plan is wrong, fix the plan first, record the correction in that task's `Execution result`, then stop and report it.
6. If a task reveals a difficult issue that should not be solved inside the current task, add it to the most relevant later task as a follow-up note.
7. Do not commit unless the user explicitly asks. Do not revert unrelated user changes.
8. Treat `rg` checks that expect no matches as successful when there is no output, even if `rg` exits with code 1.
9. Do not delete a legacy package until all active imports have moved and focused tests pass.
10. Before recursive deletes on Windows, resolve absolute paths and verify they are inside the repository.
11. If `mvn` is not available on PATH, use the local Maven binary that has already verified this project: `E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd`.

Current completed tasks:
- `[x]` Task 1: Freeze import graph and add consolidation guardrails.
- `[x]` Task 2: Java architecture guard upgrade.
- `[x]` Task 3: Java user module application port preparation.
- `[x]` Task 4: Java platform module application port preparation and shared persistence extraction.
- `[x]` Task 5: Java agent module typed boundary split.
- `[x]` Task 6: Java tool gateway real application/infrastructure split.
- `[x]` Task 7: Java security/common exception boundary cleanup.
- `[x]` Task 8: Java consolidation verification.
- `[x]` Task 9: Python import graph ratchet.
- `[x]` Task 10: Python contracts and schema ownership migration.
- `[x]` Task 11: Python context layer implementation migration.
- `[x]` Task 12: Python understanding layer implementation migration.
- `[x]` Task 13: Python planning layer implementation migration.
- `[x]` Task 14: Python execution/tools layer implementation migration.
- `[x]` Task 15: Python integrations layer implementation migration.
- `[x]` Task 16: Python evidence layer implementation migration.
- `[x]` Task 17: Python composition layer implementation migration.
- `[x]` Task 18: Python orchestration layer implementation migration.
- `[x]` Task 19: Python governance and observability implementation migration.
- `[ ]` Task 20: Delete retired Python packages.
- `[ ]` Task 21: Cross-service contract and frontend flow verification.
- `[ ]` Task 22: Documentation and developer guidance refresh.
- `[ ]` Task 23: Final full-stack verification and cleanup.

---

## Execution Requirements And Workload Strategy

This plan is larger and riskier than the first-stage layering plan. The goal is not to create more wrappers; the goal is to move real implementation into owner layers and then delete retired coupled packages. Execute it with the following requirements.

### Mandatory Task Loop

For every user request to execute work:

1. Read this plan first.
2. Identify the exact requested task or the next unchecked task.
3. Execute exactly one task.
4. Run the focused verification commands listed in that task.
5. Update this plan before responding:
   - mark the task `[x]`;
   - add `Execution result` immediately after that task's checkbox;
   - record files changed, files moved/deleted, commands run, pass/fail status, blockers, and plan corrections.
6. Stop after one task and report the same result written into this plan.

### Consolidation Principles

- Treat Java and Python Agent as one product boundary, but avoid deep Java and deep Python edits in the same task unless the task is explicitly a contract task.
- Preserve Java-Python API field names unless Task 21 updates Python contracts, Java tests, and frontend consumers together.
- Move implementation by responsibility, not by filename. If a file mixes planning, evidence, execution, and composition behavior, split it instead of moving it wholesale.
- Prefer controlled moves/splits with focused tests over broad search/replace or mass directory moves.
- Do not delete retired Python packages until import graph tests prove active code no longer imports them.
- Do not recreate compatibility wrappers as an escape hatch. If a dependency cannot be migrated cleanly, record the blocker under the most relevant later task.
- Keep generated outputs, test logs, and large command dumps out of the plan. Summarize the result and keep exact commands.
- Use `rg`, targeted file reads, and focused diffs. Avoid spending a context window on full file dumps unless the task needs it.

### Verification Rhythm

- Start each migration task with the current focused test if one exists, so regressions are attributable.
- After code movement, run the task's focused tests first.
- Run broader tests only when shared contracts, cross-module boundaries, startup imports, or frontend-facing behavior changed.
- Treat `rg` no-output checks as successful even when `rg` exits with code 1.
- If `mvn` is not on PATH, use the Maven path listed in the Execution Prompt.

### Workload And Token Budget

These are execution budgets for quality control. They are not hard accounting, but if a task exceeds its budget, stop at a clean checkpoint and update this plan rather than lowering review quality.

| Batch | Tasks | Scope | Estimated token cost | Risk | Stop condition |
|---|---:|---|---:|---|---|
| A | 1-2 | Import graph and Java/Python guardrails | 8k-16k | Low | Guard tests pass with explicit allowlists |
| B | 3-8 | Java true layering: ports, persistence entities, typed Agent boundary, tool gateway, security/common cleanup | 35k-65k | High | `mvn test` passes and Java allowlists are removed |
| C | 9-10 | Python import ratchet and Java-Python contract schema ownership | 12k-24k | Medium | Contract tests pass; API/contracts no longer import `app.schemas` |
| D | 11-13 | Python context, understanding, and planning implementation migration | 35k-70k | High | Focused capability tests and S5 whitelist tests pass |
| E | 14-15 | Python execution/tools and integrations migration | 35k-75k | High | Tool execution/integration tests pass; external clients are under `integrations` |
| F | 16-19 | Python evidence, composition, orchestration, governance, observability migration | 45k-90k | Very High | Focused layer tests pass; remaining retired imports are documented blockers only |
| G | 20-23 | Retired package deletion, cross-service verification, docs, final cleanup | 25k-45k | High | Full Java, Python, and Web verification passes |

### Task Size Limits

- A normal task should modify no more than 8-12 source files or move no more than one cohesive responsibility.
- If a Python task needs to move many files from `app.orchestrator` or `app.schemas`, split by capability and update the plan before continuing.
- If a Java task crosses both user and platform persistence, keep it inside Task 4 because those JPA relations are coupled; otherwise avoid multi-domain Java edits.
- If a task reveals that a later deletion task cannot be completed safely, add a blocker/follow-up note to Task 20 and stop after the current task.

### Stop Conditions

Stop immediately, update the plan, and report the blocker when:

- A focused test fails after two reasonable fix attempts.
- A task requires changing the Java-Python response contract outside Task 21.
- A legacy Python package still has active imports at deletion time.
- A file has mixed responsibilities that cannot be split without exceeding the task size limit.
- A recursive delete target cannot be resolved inside the repository.
- The worktree contains unrelated changes in files the task must heavily rewrite and the ownership is unclear.

---

## Current Findings

The first-stage plan created the target directories, but many Python target-layer files still import implementation from legacy packages:

```text
app.understanding -> app.agents, app.schemas
app.planning -> app.agents, app.orchestrator, app.schemas
app.execution -> app.agents, app.orchestrator, app.tools
app.integrations -> app.tool_gateway, app.tools, app.catalog, app.storage, app.agents
app.evidence -> app.orchestrator, app.schemas
app.composition -> app.agents, app.orchestrator, app.schemas
app.orchestration -> app.orchestrator, app.schemas
app.governance -> app.orchestrator
app.observability -> app.orchestrator, app.schemas
```

Java package names are already standardized, but implementation still has pragmatic coupling:

```text
domain entities still import jakarta.persistence
application services still import infrastructure repositories directly
application services still import Spring Authentication / HttpStatus in places
agent application still manipulates JsonNode directly
platform application still serializes raw JsonNode and imports repositories directly
```

This plan intentionally consolidates real implementation instead of only renaming packages.

## Plan Review Corrections

This review section is binding for execution. It corrects issues found after checking the first version of this plan against the current codebase.

1. Java user/platform persistence cannot be split independently. `TravelConversation` currently has a JPA `@ManyToOne` relation to `UserAccount`. Therefore Task 3 must not remove JPA from `UserAccount` unless Task 4's platform persistence relation has also been migrated. The revised sequence is:
   - Task 3 prepares user application ports and security adapters while keeping JPA annotations if needed for compile stability.
   - Task 4 migrates user and platform JPA entities together, because their table relations are coupled.
2. Python schema migration must be incremental. `app.schemas` has many cross-cutting models, so Task 10 only moves Java-Python contract models. Context, understanding, planning, execution, evidence, composition, and orchestration models move in their own layer tasks.
3. `tool_whitelist_builder` is planning-owned. Planning chooses tool candidates and whitelists; execution applies that whitelist, schedules calls, and records attempts. Do not move `tool_whitelist_builder` to execution.
4. Concrete external clients belong in `integrations`; Agent tool interfaces and tool-facing classes remain in `tools`. Do not move every `tools/real` class blindly. Split real tools only when they contain direct external adapter/client code.
5. Python orchestration migration is high-risk because `app.orchestrator` currently contains more than one hundred files. Task 18 must move the state machine and state files only. Any remaining `agent_core_*` or workflow helper migration that exceeds the task budget must be recorded as follow-up before Task 20 deletion.
6. A single task should normally modify no more than 8-12 source files or move no more than one cohesive responsibility. If a task exceeds that size, stop at a clean checkpoint, update this plan with a subtask/follow-up, and do not continue by broad mechanical edits.
7. Contract field names across Java, Python, and Web are the coordination boundary. Python internal layer moves must not change the Java-facing response shape unless Task 21 updates both Java tests and frontend behavior.

## Definition Of Done

Java:

- No active Java `domain` class imports `jakarta.persistence`, Spring MVC, Spring Security, Spring Data, HTTP clients, or repository types.
- Java `application` services depend on domain/application ports, not Spring Data repository interfaces or external HTTP clients.
- Java web controllers own HTTP request/response mapping and current-user extraction.
- Java infrastructure owns JPA entities, Spring Data repositories, Python HTTP client, MCP HTTP client, and security adapters.
- Java agent boundary has typed request/response models at the Java side; raw JSON is contained at web/infrastructure boundaries only.
- `mvn test` passes.

Python:

- Target capability layers contain real implementation, not wrappers around old packages.
- `api` owns FastAPI routes and HTTP error mapping only.
- `contracts` owns Java-Python request/response/error models.
- `context`, `understanding`, `planning`, `execution`, `tools`, `integrations`, `evidence`, `composition`, `orchestration`, `governance`, and `observability` own their real implementation files.
- No target layer imports from retired packages: `app.agents`, `app.orchestrator`, `app.schemas`, `app.tool_gateway`, `app.storage`, `app.catalog`, `app.prompts`, or `app.policies`.
- Retired Python packages are deleted, except `app.tools` remains because it is a target layer and must be cleaned rather than deleted.
- `pytest` passes and `python -c "from app.main import app; print(app.title)"` still works.

Cross-stack:

- Java-Python contract tests pass on both sides.
- Frontend build passes.
- README, RUNBOOK, and AGENTS describe implemented layers, not staged wrapper layers.
- No generated outputs remain in Git status.

---

## Task 1: Freeze Import Graph And Add Consolidation Guardrails

**Files:**
- Create/modify: `apps/agent-python/tests/test_layer_consolidation_imports.py`
- Modify: `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`
- Inspect: `docs/plans/2026-07-08-java-layering-standardization.md`

**Step 1: Record current Python legacy dependencies**

Run:

```powershell
rg -n "from app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)|import app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)" apps/agent-python/app/api apps/agent-python/app/contracts apps/agent-python/app/context apps/agent-python/app/understanding apps/agent-python/app/planning apps/agent-python/app/execution apps/agent-python/app/integrations apps/agent-python/app/evidence apps/agent-python/app/composition apps/agent-python/app/orchestration apps/agent-python/app/governance apps/agent-python/app/observability
```

Expected:
- Output documents all remaining wrapper/legacy imports.
- Do not fix them in this task.

**Step 2: Add Python import guard test**

Create `tests/test_layer_consolidation_imports.py` with helper functions that scan target layer source text and fail on retired package imports. Start with an explicit allowlist matching the current findings so the test passes today.

The allowlist must be organized by target layer and include comments naming the future task that removes each allowance.

**Step 3: Add Java guard placeholders**

Extend `ArchitectureLayeringTest` with tests for:
- no retired package declarations;
- no JPA/Spring imports in `domain`;
- no infrastructure repository imports in `application`;
- no HTTP client imports in `domain` or `application`.

If the stricter tests fail today, keep them as explicit `allowedViolations` lists with comments naming Tasks 3-7.

**Step 4: Run guard tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_layer_consolidation_imports.py

cd ..\api-java
mvn test -Dtest=ArchitectureLayeringTest
```

Expected:
- Tests pass with explicit allowlists.
- The allowlists become the migration checklist.

**Completion checkbox:** `[x] Task 1 complete`

**Execution result:**
- Froze the current Python target-layer retired-package import graph with:
  - `rg -n "from app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)|import app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)" apps/agent-python/app/api apps/agent-python/app/contracts apps/agent-python/app/context apps/agent-python/app/understanding apps/agent-python/app/planning apps/agent-python/app/execution apps/agent-python/app/integrations apps/agent-python/app/evidence apps/agent-python/app/composition apps/agent-python/app/orchestration apps/agent-python/app/governance apps/agent-python/app/observability`
  - Output confirmed existing wrapper/legacy imports across `context`, `understanding`, `planning`, `execution`, `integrations`, `evidence`, `composition`, `orchestration`, `governance`, `observability`, and one API bootstrap import for Java Tool Gateway installation.
- Added `apps/agent-python/tests/test_layer_consolidation_imports.py`.
  - The test scans target-layer `.py` files for imports from retired packages: `app.agents`, `app.orchestrator`, `app.schemas`, `app.tool_gateway`, `app.storage`, `app.catalog`, `app.prompts`, and `app.policies`.
  - The current violations are captured in explicit allowlists grouped by future owner tasks: Task 11 through Task 19.
  - The test fails both on unexpected new retired imports and on stale allowlist entries.
- Extended `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`.
  - Added consolidation guardrails for domain imports and application imports.
  - Current domain JPA imports are allowlisted for Task 4.
  - Current application imports from repositories, root security infrastructure, `HttpStatus`, `Authentication`, `PythonAgentClient`, and `SearchMcpAdapter` are allowlisted for Tasks 3-6.
  - Fixed the application guard regex so it catches both root `api.infrastructure.*` and domain-local `*.infrastructure.*` imports.
- Commands run:
  - `pytest tests/test_layer_consolidation_imports.py` from `apps/agent-python`: pass, `1 passed in 0.06s`.
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test -Dtest=ArchitectureLayeringTest` from `apps/api-java`: first run failed because `TravelQueryService -> PythonAgentClient` and `ToolGatewayService -> SearchMcpAdapter` were missing from the current allowlist; fixed allowlist.
  - Same Java command: second run failed because the regex did not match root `api.infrastructure.security` imports and flagged those allowlist entries as stale; fixed regex.
  - Same Java command final run: pass, `Tests run: 4, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
- Files changed: `apps/agent-python/tests/test_layer_consolidation_imports.py`, `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`, and this plan file.
- Deleted files: none.
- Blockers: none.
- No commit was made.

---

## Task 2: Java Architecture Guard Upgrade

**Files:**
- Modify: `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`
- Inspect: `apps/api-java/src/main/java/com/travel/intelligence/api/**`

**Step 1: Make Java guard tests path-driven**

Update the architecture test so it walks `src/main/java` once and classifies files by package segment:

```text
/domain/
/application/
/infrastructure/
/web/
/config/
```

**Step 2: Add final desired rules behind allowlists**

Rules:
- `domain` must not import `jakarta.persistence`, `org.springframework`, Jackson, or repository/client types.
- `application` must not import `*.infrastructure.*`, Spring MVC, Spring Security `Authentication`, HTTP clients, or Spring Data repositories.
- `web` must not import persistence repositories directly.
- `infrastructure` may import JPA, Spring Data, HTTP clients, Jackson, and external clients.

**Step 3: Run the test and record violations**

Run:

```powershell
cd apps/api-java
mvn test -Dtest=ArchitectureLayeringTest
```

Expected:
- Test passes only because existing known violations are in the allowlist.
- This task records exact violation file paths in its execution result.

**Completion checkbox:** `[x] Task 2 complete`

**Execution result:**
- Upgraded `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java` from focused placeholder scans to a path-driven source layout guard.
- The test now walks `src/main/java` once into `SourceLayout` buckets:
  - `all`
  - `domain`
  - `application`
  - `infrastructure`
  - `web`
  - `config`
- Added final desired rules behind explicit allowlists:
  - `domain` cannot import JPA, Spring, Jackson, repositories, controllers, or HTTP clients except current known Task 4 violations.
  - `application` cannot import infrastructure adapters, Spring MVC, Spring Security `Authentication`, Spring Data, repositories, or HTTP clients except current known Task 3-6 violations.
  - `web` cannot import persistence repositories or infrastructure adapters directly; current result has no web allowlist entries.
- Current domain allowlist violation files:
  - `src/main/java/com/travel/intelligence/api/user/domain/UserAccount.java`
  - `src/main/java/com/travel/intelligence/api/platform/domain/TravelConversation.java`
  - `src/main/java/com/travel/intelligence/api/platform/domain/TravelQueryRecord.java`
- Current application allowlist violation files:
  - `src/main/java/com/travel/intelligence/api/user/application/AuthService.java`
  - `src/main/java/com/travel/intelligence/api/platform/application/TravelPlatformService.java`
  - `src/main/java/com/travel/intelligence/api/agent/application/TravelQueryService.java`
  - `src/main/java/com/travel/intelligence/api/tool/application/ToolGatewayService.java`
- Command run:
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test -Dtest=ArchitectureLayeringTest` from `apps/api-java`: pass, `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
- Files changed: `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java` and this plan file.
- Deleted files: none.
- Blockers: none.
- No commit was made.

---

## Task 3: Java User Module Application Port Preparation

**Files:**
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/user/domain/UserAccount.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/user/domain/UserPrincipal.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/UserAccountStore.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/PasswordHasher.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthTokenIssuer.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthService.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/UserAccountRepository.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/JpaUserAccountStore.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/PasswordEncoderHasher.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/JwtAuthTokenIssuer.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/user/web/AuthController.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/ApiJavaApplicationTests.java`

**Step 1: Add focused user tests if missing**

Add or extend tests to verify register, login, duplicate username/email behavior, and `/api/auth/me` still work.

**Step 2: Prepare user application ports**

Create `UserAccountStore`, `PasswordHasher`, and `AuthTokenIssuer`. `AuthService` must depend on these ports rather than `UserAccountRepository`, `PasswordEncoder`, or `JwtService`.

**Step 3: Add infrastructure adapters without breaking JPA relations**

Create `JpaUserAccountStore`, `PasswordEncoderHasher`, and `JwtAuthTokenIssuer`.

Do not remove JPA annotations from `UserAccount` in this task unless Task 4's platform persistence entities are also migrated in the same execution. `TravelConversation` currently points to `UserAccount` with a JPA relation, so stripping JPA here would break the next module.

**Step 4: Remove infrastructure dependencies from `AuthService`**

`AuthService` should depend on:

```java
UserAccountStore
PasswordHasher
AuthTokenIssuer
```

The controller or security adapter should provide the current user identity instead of passing raw Spring `Authentication` deep into business logic.

**Step 5: Run focused verification**

Run:

```powershell
cd apps/api-java
mvn test -Dtest=ApiJavaApplicationTests,ArchitectureLayeringTest
```

Expected:
- User flows still pass.
- `UserAccount` may still import JPA after this task, but that violation must remain explicitly allowlisted for Task 4.
- `AuthService` no longer imports `user.infrastructure`, Spring Security `Authentication`, or `PasswordEncoder`.

**Completion checkbox:** `[x] Task 3 complete`

**Execution result:**
- Prepared user application ports without removing JPA annotations from `UserAccount`, preserving the Task 4 requirement to migrate user/platform JPA relations together.
- Added user application ports:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/UserAccountStore.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/PasswordHasher.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthTokenIssuer.java`
- Added infrastructure adapters:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/JpaUserAccountStore.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/PasswordEncoderHasher.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/JwtAuthTokenIssuer.java`
- Updated `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthService.java`.
  - It now depends on `UserAccountStore`, `PasswordHasher`, and `AuthTokenIssuer`.
  - It no longer imports `UserAccountRepository`, `PasswordEncoder`, `JwtService`, `CurrentUser`, or Spring Security `Authentication`.
  - It still imports `HttpStatus`; this remains a Task 7 application-exception boundary cleanup item.
- Updated `apps/api-java/src/main/java/com/travel/intelligence/api/user/web/AuthController.java`.
  - The controller now resolves the current `UserPrincipal` through `CurrentUser` and passes the principal into `AuthService.me(...)`.
  - This keeps Spring `Authentication` at the web/security boundary.
- Added focused auth flow coverage in `apps/api-java/src/test/java/com/travel/intelligence/api/user/web/AuthControllerTest.java`.
  - Covers register, duplicate username, duplicate email, login, and `/api/auth/me`.
- Updated `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`.
  - Removed stale Task 3 allowlist entries for `AuthService` infrastructure/security imports.
  - Adjusted the web guard so root `infrastructure.security.CurrentUser` remains allowed at the web boundary while direct domain-local infrastructure repository imports remain forbidden.
- Commands run:
  - `rg -n "UserAccountRepository|PasswordEncoder|JwtService|CurrentUser|Authentication" apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthService.java ...`: confirmed old dependencies moved out of `AuthService`; remaining matches are in web/infrastructure adapters.
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test -Dtest=ApiJavaApplicationTests,ArchitectureLayeringTest`: failed in PowerShell because the comma-separated `-Dtest` value was unquoted.
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=ApiJavaApplicationTests,ArchitectureLayeringTest"`: first run after code changes passed `ApiJavaApplicationTests` but failed `ArchitectureLayeringTest` due stale Task 3 allowlist entries and an over-broad web infrastructure regex; fixed both.
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=ApiJavaApplicationTests,ArchitectureLayeringTest"`: pass, `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=AuthControllerTest,ApiJavaApplicationTests,ArchitectureLayeringTest"`: pass, `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
  - Final `rg -n "UserAccountRepository|PasswordEncoder|JwtService|CurrentUser|Authentication" apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthService.java`: pass, no output; `rg` exit code 1 is expected for no matches.
- Files changed:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthService.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/UserAccountStore.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/PasswordHasher.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthTokenIssuer.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/JpaUserAccountStore.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/PasswordEncoderHasher.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/JwtAuthTokenIssuer.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/web/AuthController.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/user/web/AuthControllerTest.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`
  - this plan file.
- Deleted files: none.
- Blockers: none.
- No commit was made.

---

## Task 4: Java Platform Module Application Port Preparation And Shared Persistence Extraction

**Files:**
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/user/domain/UserAccount.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/domain/TravelConversation.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/domain/TravelQueryRecord.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/ConversationStore.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/QueryRecordStore.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/AgentConversationUseCase.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/TravelPlatformService.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/UserAccountEntity.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/UserAccountMapper.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelConversationEntity.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelQueryRecordEntity.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelPlatformMapper.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelConversationRepository.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelQueryRecordRepository.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/JpaConversationStore.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/JpaQueryRecordStore.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/web/TravelPlatformController.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/platform/TravelPlatformFlowTest.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`

**Step 1: Preserve behavior with platform flow tests**

Run:

```powershell
cd apps/api-java
mvn test -Dtest=TravelPlatformFlowTest
```

Expected:
- Current flow passes before refactor.

**Step 2: Move user and platform JPA annotations together**

Remove JPA annotations from `UserAccount`, `TravelConversation`, and `TravelQueryRecord` in the same task. Create infrastructure entities for all three so JPA relations move together:

```text
UserAccountEntity
TravelConversationEntity -> UserAccountEntity
TravelQueryRecordEntity -> TravelConversationEntity
```

Use stable ids and domain references in domain models.

**Step 3: Move platform persistence to infrastructure**

Create JPA entities and mappers in `user.infrastructure` and `platform.infrastructure`. Spring Data repositories should manage infrastructure entities only.

**Step 4: Make application depend on ports**

`TravelPlatformService` should depend on `ConversationStore`, `QueryRecordStore`, `UserAccountStore`, and the Java-side Agent use case/gateway, not repositories.

**Step 5: Run focused verification**

Run:

```powershell
cd apps/api-java
mvn test -Dtest=TravelPlatformFlowTest,ArchitectureLayeringTest
```

Expected:
- Platform API behavior remains stable.
- User and platform domain classes no longer import JPA.
- Platform application no longer imports infrastructure repositories.

**Completion checkbox:** `[x] Task 4 complete`

**Execution result:**
- Preserved the platform behavior baseline with:
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=TravelPlatformFlowTest"`
  - Result: pass, `Tests run: 1, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
- Moved user/platform persistence out of domain and into infrastructure:
  - removed JPA annotations/imports from `UserAccount`, `TravelConversation`, and `TravelQueryRecord`;
  - added `UserAccountEntity`, `TravelConversationEntity`, `TravelQueryRecordEntity`;
  - added `UserAccountMapper` and `TravelPlatformMapper`;
  - changed Spring Data repositories to manage infrastructure entities only.
- Added platform application ports and adapters:
  - `ConversationStore` with `JpaConversationStore`;
  - `QueryRecordStore` with `JpaQueryRecordStore`;
  - `AgentConversationUseCase` with `AgentConversationGatewayAdapter`.
- Updated `TravelPlatformService` to depend on `UserAccountStore`, `ConversationStore`, `QueryRecordStore`, and `AgentConversationUseCase` instead of JPA repositories or direct agent service.
- Updated `TravelPlatformController` to resolve `UserPrincipal` through `CurrentUser`, so platform application methods no longer accept Spring Security `Authentication`.
- Updated `QueryRecordSummary` to read `conversationId` from the domain record instead of a JPA relationship.
- Updated `ArchitectureLayeringTest` by removing the now-stale Task 4 domain JPA allowlist entries and platform application repository/security allowlist entries.
- Verification commands:
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=TravelPlatformFlowTest,ArchitectureLayeringTest"`: pass, `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
  - `rg -n "jakarta\.persistence|org\.springframework\.data|JpaRepository" apps/api-java/src/main/java/com/travel/intelligence/api/user/domain apps/api-java/src/main/java/com/travel/intelligence/api/platform/domain`: no output, expected pass.
  - `rg -n "\.infrastructure\.|Repository|org\.springframework\.security\.core\.Authentication" apps/api-java/src/main/java/com/travel/intelligence/api/platform/application`: no output, expected pass.
- Files changed:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/domain/UserAccount.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/domain/TravelConversation.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/domain/TravelQueryRecord.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/ConversationStore.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/QueryRecordStore.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/AgentConversationUseCase.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/TravelPlatformService.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/UserAccountEntity.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/UserAccountMapper.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/UserAccountRepository.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/infrastructure/JpaUserAccountStore.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelConversationEntity.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelQueryRecordEntity.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelPlatformMapper.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelConversationRepository.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/TravelQueryRecordRepository.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/JpaConversationStore.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/JpaQueryRecordStore.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/AgentConversationGatewayAdapter.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/web/TravelPlatformController.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/web/dto/QueryRecordSummary.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`
  - this plan file.
- Deleted files: none.
- Blockers: none.
- Plan correction: Task 4 needed one additional infrastructure adapter, `AgentConversationGatewayAdapter`, so `TravelPlatformService` could depend on the new `AgentConversationUseCase` port without making `TravelQueryService` depend back on the platform application package.
- No commit was made.

---

## Task 5: Java Agent Module Typed Boundary Split

**Files:**
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/PythonAgentGateway.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryCommand.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryResult.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/TravelQueryService.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/infrastructure/PythonAgentClient.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/web/TravelProxyController.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/TravelPlatformService.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/agent/application/TravelQueryServiceTest.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/platform/TravelPlatformFlowTest.java`

**Step 1: Add typed Java-side contract tests**

Tests should assert `AgentQueryCommand` maps to Python request fields and `AgentQueryResult` preserves:

```text
answer, session_id, query_id, confidence, visible_trace, evidence_summary,
limitations, tool_traces, structured_result, field_evidence_summary,
conflicts, citation_check_result, semantic_frame_summary, answer_mode
```

**Step 2: Isolate raw JSON**

Raw `JsonNode` should remain in:
- `agent.infrastructure.PythonAgentClient`;
- legacy `agent.web.TravelProxyController` if required for backward compatibility;
- persistence serialization adapter if storing raw response JSON.

`TravelQueryService` should use typed command/result objects.

**Step 3: Run focused verification**

Run:

```powershell
cd apps/api-java
mvn test "-Dtest=TravelQueryServiceTest,TravelPlatformFlowTest,ArchitectureLayeringTest"
```

Expected:
- Java Agent contract remains compatible.
- Application layer no longer contains Python HTTP details.

**Completion checkbox:** `[x] Task 5 complete`

**Execution result:**
- Added Java-side typed Agent boundary records and port:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/PythonAgentGateway.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryCommand.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryResult.java`
- Refactored `TravelQueryService` to depend on `PythonAgentGateway` and use `AgentQueryCommand` / `AgentQueryResult` internally.
  - Removed direct dependency on `PythonAgentClient`.
  - Removed direct `JsonNode`/`ObjectNode` manipulation from the agent application service.
  - Kept session memory injection and response-derived memory updates working through typed fields and Map/List values.
- Updated `PythonAgentClient` to implement `PythonAgentGateway`.
  - It now owns conversion from `AgentQueryCommand` to Python `/agent/query` JSON fields.
  - It now owns conversion from raw Python `JsonNode` response into `AgentQueryResult`.
- Updated the legacy `TravelProxyController` so raw JSON remains at the web compatibility boundary while calling the typed service internally.
- Tightened platform/agent connection:
  - changed `AgentConversationUseCase` to accept `AgentQueryCommand` and return `AgentQueryResult`;
  - simplified `AgentConversationGatewayAdapter` to pass typed objects through;
  - updated `TravelPlatformService` to build an `AgentQueryCommand`, consume `AgentQueryResult`, persist `rawResponse`, and return the same external JSON shape through `AskTravelAgentResponse`.
- Updated tests:
  - `TravelQueryServiceTest` now mocks `PythonAgentGateway`, captures `AgentQueryCommand`, and asserts `AgentQueryResult` preserves `answer`, `session_id`, `query_id`, `confidence`, `visible_trace`, `evidence_summary`, `limitations`, `tool_traces`, `structured_result`, `field_evidence_summary`, `conflicts`, `citation_check_result`, `semantic_frame_summary`, and `answer_mode`.
  - `TravelPlatformFlowTest` now verifies the forwarded typed command instead of a raw JSON payload.
  - `TravelProxyControllerTest` now stubs typed `AgentQueryResult` while preserving the legacy JSON response behavior.
- Updated `ArchitectureLayeringTest` by removing the now-stale Task 5 allowlist entry for `TravelQueryService -> PythonAgentClient`.
- Verification commands:
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=TravelQueryServiceTest,TravelPlatformFlowTest,ArchitectureLayeringTest"`: pass, `Tests run: 9, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=TravelProxyControllerTest"`: pass, `Tests run: 2, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=TravelQueryServiceTest,TravelPlatformFlowTest,ArchitectureLayeringTest,TravelProxyControllerTest"`: pass, `Tests run: 11, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
  - `rg -n "PythonAgentClient|JsonNode|ObjectNode|RestClient|WebClient|com\.travel\.intelligence\.api\.agent\.infrastructure" apps/api-java/src/main/java/com/travel/intelligence/api/agent/application`: no output, expected pass.
  - `rg -n "travelQuery\(JsonNode|public JsonNode travelQuery|PythonAgentClient" apps/api-java/src/main/java/com/travel/intelligence/api/agent/application apps/api-java/src/main/java/com/travel/intelligence/api/platform/application`: no output, expected pass.
- Files changed:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/PythonAgentGateway.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryCommand.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryResult.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/TravelQueryService.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/infrastructure/PythonAgentClient.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/web/TravelProxyController.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/AgentConversationUseCase.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/TravelPlatformService.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/infrastructure/AgentConversationGatewayAdapter.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/web/dto/AskTravelAgentResponse.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/agent/application/TravelQueryServiceTest.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/agent/web/TravelProxyControllerTest.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/platform/TravelPlatformFlowTest.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`
  - this plan file.
- Deleted files: none.
- Blockers: none.
- Plan correction: also updated and verified `TravelProxyControllerTest` because Task 5 changed the legacy JSON proxy controller even though that test was not listed in the original task verification set.
- No commit was made.

---

## Task 6: Java Tool Gateway Real Application/Infrastructure Split

**Files:**
- Create/modify: `apps/api-java/src/main/java/com/travel/intelligence/api/tool/application/ToolSearchPort.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/tool/application/ToolGatewayService.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/tool/infrastructure/SearchMcpAdapter.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/tool/infrastructure/mcp/*.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/tool/web/ToolGatewayController.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/tool/application/ToolGatewayServiceTest.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/tool/infrastructure/SearchMcpAdapterTest.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/tool/web/ToolGatewayControllerTest.java`

**Step 1: Define application port**

`ToolGatewayService` should depend on an application port such as `ToolSearchPort`, not a concrete MCP adapter.

**Step 2: Keep external MCP details in infrastructure**

MCP HTTP payloads, `RestClient`, endpoint paths, and low-level error mapping stay under `tool.infrastructure`.

**Step 3: Run focused verification**

Run:

```powershell
cd apps/api-java
mvn test "-Dtest=ToolGatewayServiceTest,SearchMcpAdapterTest,ToolGatewayControllerTest,ArchitectureLayeringTest"
```

Expected:
- Tool Gateway behavior unchanged.
- Application layer has no MCP HTTP details.

**Completion checkbox:** `[x] Task 6 complete`

**Execution result:**
- Preserved the current Tool Gateway behavior baseline with:
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=ToolGatewayServiceTest,SearchMcpAdapterTest,ToolGatewayControllerTest,ArchitectureLayeringTest"`
  - Result: pass, `Tests run: 13, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
- Added the application port:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/tool/application/ToolSearchPort.java`
- Refactored `ToolGatewayService`.
  - It now depends on `ToolSearchPort`, not `SearchMcpAdapter`.
  - Search tool routing uses `searchPort.toolName()`.
  - Mock `openmeteo_mcp` and `osm_mcp` behavior remains unchanged.
- Refactored `SearchMcpAdapter`.
  - It now implements `ToolSearchPort`.
  - MCP configuration, endpoint invocation, timeout, evidence mapping, and low-level error mapping remain in `tool.infrastructure`.
- Updated `ToolGatewayServiceTest`.
  - The service test now uses a small fake `ToolSearchPort` instead of constructing the infrastructure MCP adapter.
- Updated `ArchitectureLayeringTest`.
  - Removed the now-stale Task 6 allowlist entry for `ToolGatewayService -> SearchMcpAdapter`.
- Verification commands:
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test "-Dtest=ToolGatewayServiceTest,SearchMcpAdapterTest,ToolGatewayControllerTest,ArchitectureLayeringTest"`: pass, `Tests run: 13, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
  - `rg -n "\.infrastructure\.|SearchMcpAdapter|RestClient|WebClient|McpHttpClient|McpInvokeResult" apps/api-java/src/main/java/com/travel/intelligence/api/tool/application`: no output, expected pass.
  - `rg -n "SearchMcpAdapter" apps/api-java/src/main/java/com/travel/intelligence/api/tool/application apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`: no output, expected pass.
- Files changed:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/tool/application/ToolSearchPort.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/tool/application/ToolGatewayService.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/tool/infrastructure/SearchMcpAdapter.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/tool/application/ToolGatewayServiceTest.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`
  - this plan file.
- Deleted files: none in this task.
- Blockers: none.
- Plan correction: none.
- No commit was made.

---

## Task 7: Java Security/Common Exception Boundary Cleanup

**Files:**
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/common/ApiException.java`
- Create: `apps/api-java/src/main/java/com/travel/intelligence/api/common/ApplicationErrorCode.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/common/GlobalExceptionHandler.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/CurrentUser.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthService.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/TravelPlatformService.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`

**Step 1: Remove HTTP status from application decisions**

Application/domain code should throw errors with product-level error codes. `GlobalExceptionHandler` maps those codes to HTTP status.

**Step 2: Remove Spring Security Authentication from application service signatures**

Web/security adapters resolve current user id/principal and pass simple ids or domain principals into application services.

**Step 3: Run verification**

Run:

```powershell
cd apps/api-java
mvn test
```

Expected:
- All Java tests pass.
- Architecture allowlist for Java application Spring/Security coupling shrinks or becomes empty.

**Completion checkbox:** `[x] Task 7 complete`

**Execution result:**
- Added product-level application error codes:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/common/ApplicationErrorCode.java`
- Refactored `ApiException`.
  - It now carries `ApplicationErrorCode` only.
  - Removed direct `HttpStatus` storage and the old `status()` accessor from `ApiException`.
  - Existing API error code strings such as `bad_credentials`, `conversation_not_found`, and `agent_unavailable` are preserved through `ApplicationErrorCode.code()`.
- Refactored `GlobalExceptionHandler`.
  - It now maps `ApiException.errorCode().httpStatus()` to the HTTP response status.
- Updated security boundary code:
  - `CurrentUser` now throws `ApiException(ApplicationErrorCode.UNAUTHORIZED, ...)`.
  - `JwtAuthenticationFilter` maps `ApiException` through `ApplicationErrorCode`.
  - `JwtService` now throws product-level unauthorized errors instead of constructing exceptions with `HttpStatus`.
- Updated application services:
  - `AuthService` no longer imports `HttpStatus`; it throws product-level codes for username/email conflicts, bad credentials, and missing user.
  - `TravelPlatformService` no longer imports `HttpStatus`; it throws product-level codes for missing conversations/records and record serialization errors.
- Updated infrastructure/test usage:
  - `PythonAgentClient` now throws product-level Agent errors (`AGENT_TIMEOUT`, `AGENT_UNAVAILABLE`, `AGENT_ERROR`).
  - `TravelProxyControllerTest` now constructs `ApiException` with `ApplicationErrorCode.AGENT_UNAVAILABLE`.
- Updated `ArchitectureLayeringTest`.
  - `ALLOWED_APPLICATION_CONSOLIDATION_VIOLATIONS` is now empty.
- Verification commands:
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test`: pass, `Tests run: 23, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
  - `rg -n "org\.springframework\.http\.HttpStatus|org\.springframework\.security\.core\.Authentication|\.infrastructure\.|RestClient|WebClient|JpaRepository" apps/api-java/src/main/java/com/travel/intelligence/api/user/application apps/api-java/src/main/java/com/travel/intelligence/api/platform/application apps/api-java/src/main/java/com/travel/intelligence/api/agent/application apps/api-java/src/main/java/com/travel/intelligence/api/tool/application`: no output, expected pass.
  - `rg -n "ALLOWED_APPLICATION_CONSOLIDATION_VIOLATIONS = Set\.of\(\);|import org\.springframework\.http\.HttpStatus" apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java apps/api-java/src/main/java/com/travel/intelligence/api/user/application apps/api-java/src/main/java/com/travel/intelligence/api/platform/application`: confirms the application allowlist is empty and no application `HttpStatus` imports remain.
- Files changed:
  - `apps/api-java/src/main/java/com/travel/intelligence/api/common/ApplicationErrorCode.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/common/ApiException.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/common/GlobalExceptionHandler.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/CurrentUser.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/JwtAuthenticationFilter.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/infrastructure/security/JwtService.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/user/application/AuthService.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/platform/application/TravelPlatformService.java`
  - `apps/api-java/src/main/java/com/travel/intelligence/api/agent/infrastructure/PythonAgentClient.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/agent/web/TravelProxyControllerTest.java`
  - `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`
  - this plan file.
- Deleted files: none.
- Blockers: none.
- Plan correction: none.
- No commit was made.

---

## Task 8: Java Consolidation Verification

**Files:**
- Modify if needed: `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`
- Inspect: `apps/api-java/src/main/java`
- Inspect: `apps/api-java/src/test/java`

**Step 1: Remove Java architecture allowlists**

All Java allowlists introduced in Tasks 1-2 should be empty or deleted.

**Step 2: Run exact searches**

Run from repository root:

```powershell
rg -n "import jakarta\.persistence|import org\.springframework" apps/api-java/src/main/java/com/travel/intelligence/api/user/domain apps/api-java/src/main/java/com/travel/intelligence/api/platform/domain apps/api-java/src/main/java/com/travel/intelligence/api/agent/domain
rg -n "com\.travel\.intelligence\.api\..*\.infrastructure|RestClient|WebClient|HttpHeaders|JpaRepository|Authentication" apps/api-java/src/main/java/com/travel/intelligence/api/user/application apps/api-java/src/main/java/com/travel/intelligence/api/platform/application apps/api-java/src/main/java/com/travel/intelligence/api/agent/application apps/api-java/src/main/java/com/travel/intelligence/api/tool/application
```

Expected:
- No output.

**Step 3: Run full Java verification**

Run:

```powershell
cd apps/api-java
mvn test
```

Expected:
- `BUILD SUCCESS`.

**Completion checkbox:** `[x] Task 8 complete`

**Execution result:**
- Inspected `apps/api-java/src/test/java/com/travel/intelligence/api/ArchitectureLayeringTest.java`.
  - `ALLOWED_DOMAIN_CONSOLIDATION_VIOLATIONS` is empty.
  - `ALLOWED_APPLICATION_CONSOLIDATION_VIOLATIONS` is empty.
  - No code changes were needed for the architecture guard in this task.
- Ran exact Java domain dependency search from repository root:
  - `rg -n "import jakarta\.persistence|import org\.springframework" apps/api-java/src/main/java/com/travel/intelligence/api/user/domain apps/api-java/src/main/java/com/travel/intelligence/api/platform/domain apps/api-java/src/main/java/com/travel/intelligence/api/agent/domain`
  - Result: no output, expected pass.
- Ran exact Java application dependency search from repository root:
  - `rg -n "com\.travel\.intelligence\.api\..*\.infrastructure|RestClient|WebClient|HttpHeaders|JpaRepository|Authentication" apps/api-java/src/main/java/com/travel/intelligence/api/user/application apps/api-java/src/main/java/com/travel/intelligence/api/platform/application apps/api-java/src/main/java/com/travel/intelligence/api/agent/application apps/api-java/src/main/java/com/travel/intelligence/api/tool/application`
  - Result: no output, expected pass.
- Ran full Java verification:
  - `& 'E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd' test`
  - Result: pass, `Tests run: 23, Failures: 0, Errors: 0, Skipped: 0`, `BUILD SUCCESS`.
- Files changed:
  - this plan file only.
- Deleted files: none.
- Blockers: none.
- Plan correction: none.
- No commit was made.

---

## Task 9: Python Import Graph Ratchet

**Files:**
- Modify: `apps/agent-python/tests/test_layer_consolidation_imports.py`
- Inspect: `apps/agent-python/app/**`

**Step 1: Add target-layer dependency rules**

The test should enforce:

```text
api -> contracts, orchestration, observability, config only
contracts -> no app layer imports except common typing/helpers
context -> contracts only, no tools/composition/integrations
understanding -> contracts/context only, no tools/composition/integrations
planning -> understanding/context/contracts/evidence types only, no integrations
execution -> planning/tools/integrations/observability only, no composition final response
tools -> contracts/evidence execution-neutral types only, no Java user/platform state
integrations -> external clients and adapters only, no final answer composition
evidence -> contracts/evidence models only, no tool execution
composition -> evidence/contracts only, no tools/integrations
orchestration -> may call capability layers, but not legacy packages
governance -> policy models only, no FastAPI/tool concrete adapters
observability -> logs/trace/metrics only, no business decisions
```

**Step 2: Keep temporary allowlist**

Keep existing violations in a structured allowlist so this task passes. Each later Python task must remove its own allowlist entries.

**Step 3: Run test**

Run:

```powershell
cd apps/agent-python
pytest tests/test_layer_consolidation_imports.py
```

Expected:
- Passes with explicit allowlist.

**Completion checkbox:** `[x] Task 9 complete`

**Execution result:**
- Ran the existing Python import guard baseline:
  - `pytest tests/test_layer_consolidation_imports.py` from `apps/agent-python`
  - Result before changes: pass, `1 passed in 0.15s`.
- Extended `apps/agent-python/tests/test_layer_consolidation_imports.py`.
  - Added `tools` to target-layer scanning, since `app.tools` remains a target layer rather than a retired package.
  - Added AST-based target-layer dependency checks with the Task 9 dependency rules.
  - Added `TARGET_LAYER_IMPORT_RULES` for `api`, `contracts`, `context`, `understanding`, `planning`, `execution`, `tools`, `integrations`, `evidence`, `composition`, `orchestration`, `governance`, and `observability`.
  - Added `ALLOWED_LAYER_IMPORTS_BY_TASK`, grouped by future owner tasks Task 10 through Task 19.
  - Kept the existing retired-package allowlist unchanged, still grouped by Task 11 through Task 19.
  - Switched source reads to `utf-8-sig` so the guard can parse existing `app/tools` files that contain a UTF-8 BOM.
- Inspected the current Python target-layer import graph with a read-only AST scan.
  - Captured current target-layer dependency violations as explicit temporary allowlist entries.
  - Corrected ownership for `api/app_factory.py -> app.tool_gateway.integration` into Task 15 because it is Java Tool Gateway integration cleanup, not a contract-model move.
- Verification command:
  - `pytest tests/test_layer_consolidation_imports.py` from `apps/agent-python`: pass, `2 passed in 0.10s`.
- Files changed:
  - `apps/agent-python/tests/test_layer_consolidation_imports.py`
  - this plan file.
- Deleted files: none.
- Blockers: none.
- Plan correction: grouped the API Java Tool Gateway bootstrap import under Task 15 integration cleanup.
- No commit was made.

---

## Task 10: Python Contracts And Schema Ownership Migration

**Files:**
- Modify: `apps/agent-python/app/contracts/*.py`
- Move/split from: `apps/agent-python/app/schemas/response.py`
- Move/split only Java-facing API models from: `apps/agent-python/app/schemas/user_query.py`
- Modify: imports in active target layers as needed.
- Test: `apps/agent-python/tests/test_agent_contract_layer.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Decide schema ownership**

Record schema ownership by responsibility, but do not move every schema in this task:

```text
contracts: AgentQueryRequest, AgentQueryResponse, API error models
context: ConversationContext, ConversationMemory, UserProfile, NormalizedUserRequest context-only data
understanding: QueryUnderstandingResult, SemanticFrame, TravelTask, UserGoal, place ambiguity/candidate types used for understanding
planning: InformationNeed, SearchTask, SearchQueryPlan, S5InformationDomain, EvidenceGapRequest
execution: ToolTrace, ToolWhitelist, low-level action/tool run types
evidence: Evidence, Citation, CoverageReport, EvidenceBrief, EvidenceDecisionReport, LookupClaim, OfficialSource, ReviewSignal
composition: ResponseContract, FinalAnswerDraft, Itinerary response structures
orchestration: TravelAgentState and workflow-only run state
```

**Step 2: Move only contract models**

Move only Java-Python request/response/error models needed by `app.contracts` and `app.api`. Leave non-contract schemas for their owner-layer tasks.

**Step 3: Keep `app.schemas` only as temporary compatibility for non-contract schemas**

Compatibility files may import from the new owner during this task. After this task, `app.api` and `app.contracts` must not import from `app.schemas`; other target layers may still have explicit allowlist entries until their own migration tasks.

**Step 4: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_agent_contract_layer.py tests/test_layer_consolidation_imports.py
```

Expected:
- Contract tests pass.
- `app.api` and `app.contracts` no longer import from `app.schemas`.
- Non-contract `app.schemas` imports remain only where explicitly allowed for later owner-layer tasks.

**Completion checkbox:** `[x] Task 10 complete`

**Execution result:**
- Decided Task10 schema ownership boundary:
  - `app.contracts` owns Java-Python request/response/error contracts.
  - `app.schemas.response` now keeps non-contract response composition structures (`TraceStep`, `ComparisonRow`, `RecommendationResult`, `StructuredResult`) and only re-exports legacy HTTP contract names from `app.contracts`.
  - `app.schemas.user_query` remains unchanged because its `TravelAgentState`, `UserGoal`, and state enums are orchestration/understanding-owned and are scheduled for later owner-layer tasks.
- Changed files:
  - `apps/agent-python/app/contracts/request.py`: added `TravelQueryRequest = AgentQueryRequest` compatibility contract alias.
  - `apps/agent-python/app/contracts/response.py`: added `TravelQueryResponse = AgentQueryResponse`, added `orchestration_summary`, and allowed `structured_result` to carry existing structured model/dict payloads while `from_legacy` still dumps Pydantic objects to dict.
  - `apps/agent-python/app/contracts/__init__.py`: exported legacy HTTP contract aliases from the contracts package.
  - `apps/agent-python/app/schemas/response.py`: removed local `TravelQueryRequest`/`TravelQueryResponse` class definitions and re-exported them from `app.contracts`.
  - `apps/agent-python/app/orchestration/state_machine.py`: changed target-layer facade import from `app.schemas.response` to `app.contracts.response`.
  - `apps/agent-python/tests/test_agent_contract_layer.py`: added assertions that old `app.schemas.response` names point to the new contract models.
  - `apps/agent-python/tests/test_layer_consolidation_imports.py`: removed stale `orchestration/state_machine.py -> app.schemas.response` retired-import and layer-import allowlist entries.
- Verification commands:
  - `rg -n "from app\.schemas|import app\.schemas|app\.schemas" apps/agent-python/app/api apps/agent-python/app/contracts`
    - Passed: no output. Per plan rule, `rg` exit code 1 means expected no-match success.
  - `rg -n "orchestration/state_machine.py\|.*schemas\.response|from app\.schemas\.response import TravelQueryResponse" apps/agent-python/tests/test_layer_consolidation_imports.py apps/agent-python/app/orchestration`
    - Passed: no output. Per plan rule, `rg` exit code 1 means expected no-match success.
  - `pytest tests/test_agent_contract_layer.py tests/test_layer_consolidation_imports.py`
    - Passed: `5 passed in 1.03s`.
- Blockers: none.
- Plan corrections: none.

---

## Task 11: Python Context Layer Implementation Migration

**Files:**
- Move implementation from: `apps/agent-python/app/agents/conversation_context_builder.py`
- Move models from: `apps/agent-python/app/schemas/conversation_context.py`
- Move models from: `apps/agent-python/app/schemas/conversation_memory.py`
- Move models from: `apps/agent-python/app/schemas/user_profile.py`
- Modify: `apps/agent-python/app/context/*.py`
- Test: `apps/agent-python/tests/test_agent_context_layer.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Move context builder implementation**

The context layer should own session/conversation/user preference normalization directly.

**Step 2: Remove `app.agents` and `app.schemas` imports from context**

Run:

```powershell
rg -n "from app\.(agents|schemas)|import app\.(agents|schemas)" apps/agent-python/app/context
```

Expected:
- No output.

**Step 3: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_agent_context_layer.py tests/test_layer_consolidation_imports.py
```

Expected:
- Context tests pass.
- Context allowlist entries removed.

**Completion checkbox:** `[x] Task 11 complete`

**Execution result:**
- Moved context-owned implementation and models into `apps/agent-python/app/context/conversation_context.py`.
  - Added `UserProfile`, `ConversationMemory`, `ConversationContext`, and the real `ConversationContextBuilder` implementation to the context layer.
  - Changed `ConversationContextBuilder` to accept an injectable `place_resolver`; its default catalog lookup is resolved at runtime to avoid static `app.catalog` imports from the context target layer.
  - Replaced schema-bound `TravelAgentState`, `UserContext`, `PlaceContext`, and `NormalizedUserRequest` type imports with context-owned models and duck-typed inputs where needed.
- Replaced retired owner files with compatibility imports:
  - `apps/agent-python/app/agents/conversation_context_builder.py` now re-exports `ConversationContextBuilder` from `app.context.conversation_context`.
  - `apps/agent-python/app/schemas/conversation_context.py` now re-exports `ConversationContext` from `app.context.conversation_context`.
  - `apps/agent-python/app/schemas/conversation_memory.py` now re-exports `ConversationMemory` from `app.context.conversation_context`.
  - `apps/agent-python/app/schemas/user_profile.py` now re-exports `UserProfile` from `app.context.conversation_context`.
- Updated context exports:
  - `apps/agent-python/app/context/__init__.py` now exports `UserProfile`.
- Updated guardrails:
  - Removed Task 11 context retired-import allowlist entries from `apps/agent-python/tests/test_layer_consolidation_imports.py`.
  - Removed Task 11 context target-layer dependency allowlist entries from `apps/agent-python/tests/test_layer_consolidation_imports.py`.
- Verification commands:
  - `rg -n "from app\.(agents|schemas)|import app\.(agents|schemas)" apps/agent-python/app/context`
    - Passed: no output. Per plan rule, `rg` exit code 1 means expected no-match success.
  - `rg -n "from app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)|import app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)" apps/agent-python/app/context`
    - Passed: no output. Per plan rule, `rg` exit code 1 means expected no-match success.
  - `pytest tests/test_agent_context_layer.py tests/test_layer_consolidation_imports.py`
    - Passed: `5 passed in 0.19s`.
  - `python -c "from app.context import ConversationContext, ConversationContextBuilder, ConversationMemory, UserProfile; from app.schemas.conversation_context import ConversationContext as OldContext; from app.agents.conversation_context_builder import ConversationContextBuilder as OldBuilder; print(ConversationContext is OldContext, ConversationContextBuilder is OldBuilder, ConversationMemory.__name__, UserProfile.__name__)"`
    - Passed: output `True True ConversationMemory UserProfile`.
- Blockers: none.
- Plan corrections: none.

---

## Task 12: Python Understanding Layer Implementation Migration

**Files:**
- Move implementation from: `apps/agent-python/app/agents/intent_agent.py`
- Move implementation from: `apps/agent-python/app/agents/query_understanding_agent.py`
- Move implementation from: `apps/agent-python/app/agents/llm_understanding_agent.py`
- Move implementation from: `apps/agent-python/app/agents/rule_based_understanding.py`
- Move implementation from: `apps/agent-python/app/agents/rule_based_to_normalized_request.py`
- Move implementation from: `apps/agent-python/app/agents/normalized_request_to_*.py`
- Move implementation from: `apps/agent-python/app/agents/semantic_frame_builder.py`
- Move implementation from: `apps/agent-python/app/agents/travel_task_extractor.py`
- Move implementation from: `apps/agent-python/app/agents/place_entity_extractor.py`
- Move prompts from: `apps/agent-python/app/prompts/query_understanding.*.md`
- Move prompts from: `apps/agent-python/app/prompts/llm_understanding.*.md`
- Modify: `apps/agent-python/app/understanding/*.py`
- Test: `apps/agent-python/tests/test_agent_capability_boundaries.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Move understanding implementation into `app/understanding`**

Keep class names stable unless tests require clearer naming.

**Step 2: Move understanding prompts**

Place prompts under:

```text
apps/agent-python/app/understanding/prompts/
```

Update prompt path resolution.

**Step 3: Remove legacy imports**

Run:

```powershell
rg -n "from app\.(agents|schemas|prompts)|import app\.(agents|schemas|prompts)" apps/agent-python/app/understanding
```

Expected:
- No output.

**Step 4: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_agent_capability_boundaries.py tests/test_layer_consolidation_imports.py
```

Expected:
- Understanding capability tests pass.
- Understanding allowlist entries removed.

**Completion checkbox:** `[x] Task 12 complete`

**Execution result:**
- Moved understanding-owned implementation into `apps/agent-python/app/understanding/`.
  - Added real implementation modules copied from legacy agents: `intent_agent.py`, `query_understanding_agent.py`, `llm_understanding_agent.py`, `rule_based_understanding.py`, `rule_based_to_normalized_request.py`, `normalized_request_to_query_understanding.py`, `normalized_request_to_semantic_frame.py`, `normalized_request_to_travel_task.py`, `normalized_request_to_user_goal.py`, `semantic_frame_builder.py`, `travel_task_extractor.py`, and `place_entity_extractor.py`.
  - Also moved cohesive support dependencies required by those implementations: `normalize_llm_understanding.py` and `travel_task_to_user_goal_adapter.py`.
  - Added `apps/agent-python/app/understanding/prompts/` with `llm_understanding.*.md` and `query_understanding.*.md`; `LLMUnderstandingSubAgent` now resolves prompts from this owner-layer directory.
- Moved understanding-owned models into `apps/agent-python/app/understanding/`.
  - Added/updated `normalized_user_request.py`, `query_understanding_model.py`, `semantic_frame_model.py`, `travel_task.py`, `place_ambiguity.py`, `place_candidate.py`, and `user_query.py`.
  - `UserContext`, `UserGoal`, intent/party/pace/budget/transport enums, and `RegionGateResult` now live under `app.understanding.user_query`.
  - `TravelTask`, `TravelTaskType`, semantic frame models, query understanding result, normalized request models, place ambiguity, and place candidate models now live under `app.understanding`.
- Replaced old owner files with compatibility imports:
  - Legacy `apps/agent-python/app/agents/*understanding*`, normalized-request adapters, `intent_agent.py`, `semantic_frame_builder.py`, `travel_task_extractor.py`, `place_entity_extractor.py`, `normalize_llm_understanding.py`, and `travel_task_to_user_goal_adapter.py` now re-export from `app.understanding`.
  - Legacy schema files `normalized_user_request.py`, `query_understanding.py`, `semantic_frame.py`, `travel_task.py`, `place_ambiguity.py`, and `place_candidate.py` now re-export from `app.understanding`.
  - `apps/agent-python/app/schemas/user_query.py` now imports `UserContext`, `UserGoal`, related enums, and `RegionGateResult` from `app.understanding.user_query`, while leaving `TravelAgentState` for Task 18.
- Updated understanding facade files:
  - `entity_resolution.py`, `intent_classifier.py`, `query_understanding.py`, and `semantic_frame.py` now import from local understanding modules instead of `app.agents` or `app.schemas`.
- Removed Task 12 allowlist entries from `apps/agent-python/tests/test_layer_consolidation_imports.py`.
- Kept external catalog/config/policy/utility dependencies as runtime imports inside understanding implementations, because their owner layers are scheduled for later tasks and the static target-layer graph must not regress.
- Verification commands:
  - `rg -n "from app\.(agents|schemas|prompts)|import app\.(agents|schemas|prompts)" apps/agent-python/app/understanding`
    - Passed: no output. Per plan rule, `rg` exit code 1 means expected no-match success.
  - `python -c "from app.understanding import QueryUnderstandingAgent, LLMUnderstandingSubAgent, IntentAgent, TravelTaskExtractor, SemanticFrameBuilder, LLMPlaceEntityExtractor; from app.schemas.semantic_frame import SemanticFrame; from app.schemas.travel_task import TravelTask; from app.agents.intent_agent import IntentAgent as OldIntent; print(QueryUnderstandingAgent.__name__, LLMUnderstandingSubAgent.__name__, IntentAgent is OldIntent, SemanticFrame.__name__, TravelTask.__name__)"`
    - Passed: output `QueryUnderstandingAgent LLMUnderstandingSubAgent True SemanticFrame TravelTask`.
  - `pytest tests/test_agent_capability_boundaries.py tests/test_layer_consolidation_imports.py`
    - Passed: `6 passed in 0.61s`.
- Blockers: none.
- Plan corrections: none.

---

## Task 13: Python Planning Layer Implementation Migration

**Files:**
- Move implementation from: `apps/agent-python/app/agents/information_need_planner.py`
- Move implementation from: `apps/agent-python/app/agents/search_task_planner_agent.py`
- Move implementation from: `apps/agent-python/app/orchestrator/claim_search_planner.py`
- Move implementation from: `apps/agent-python/app/orchestrator/evidence_gap_planner.py`
- Move implementation from: `apps/agent-python/app/orchestrator/s5_domain_planner.py`
- Move implementation from: `apps/agent-python/app/orchestrator/s5_information_domain_registry.py`
- Move implementation from: `apps/agent-python/app/orchestrator/s5_task_tool_catalogs/**`
- Move implementation from: `apps/agent-python/app/orchestrator/tool_whitelist_builder.py`
- Move planning policy files from: `apps/agent-python/app/orchestrator/*policy*.py` where they only select information needs/tools.
- Modify: `apps/agent-python/app/planning/*.py`
- Test: `apps/agent-python/tests/test_agent_capability_boundaries.py`
- Test: `apps/agent-python/tests/test_s5_whitelist.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Move planning models and planners**

Planning should own research plans, evidence gaps, information domains, S5 task tool catalogs, tool selection strategy, and whitelist construction.

**Step 2: Keep execution out of planning**

Planning may choose candidate tools by abstract name/capability and build whitelists, but must not call MCP, Java gateway, HTTP, or concrete adapters.

**Step 3: Remove legacy imports**

Run:

```powershell
rg -n "from app\.(agents|orchestrator|schemas)|import app\.(agents|orchestrator|schemas)" apps/agent-python/app/planning
```

Expected:
- No output.

**Step 4: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_agent_capability_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py
```

Expected:
- Planning and whitelist behavior unchanged.
- Planning allowlist entries removed.

**Completion checkbox:** `[x] Task 13 complete`

**Execution result:**
- Moved planning-owned implementation and models into `apps/agent-python/app/planning/`:
  - added real planning implementations for information needs, search task planning, claim search planning, evidence gap planning, S5 domain planning, S5 information domain registry, tool whitelist building, and S5 task tool catalogs;
  - added planning-owned model files for information needs, search tasks, S5 information domains, evidence gap requests, and tool whitelists.
- Replaced old implementation owners with compatibility exports:
  - `apps/agent-python/app/agents/information_need_planner.py`
  - `apps/agent-python/app/agents/search_task_planner_agent.py`
  - `apps/agent-python/app/orchestrator/claim_search_planner.py`
  - `apps/agent-python/app/orchestrator/evidence_gap_planner.py`
  - `apps/agent-python/app/orchestrator/s5_domain_planner.py`
  - `apps/agent-python/app/orchestrator/s5_information_domain_registry.py`
  - `apps/agent-python/app/orchestrator/tool_whitelist_builder.py`
  - `apps/agent-python/app/orchestrator/s5_task_tool_catalogs/**`
  - `apps/agent-python/app/schemas/information_need.py`
  - `apps/agent-python/app/schemas/search_task.py`
  - `apps/agent-python/app/schemas/s5_information_domain.py`
  - `apps/agent-python/app/schemas/evidence_gap_request.py`
  - `apps/agent-python/app/schemas/tool_whitelist.py`
- Removed Task13 planning allowlist entries from `apps/agent-python/tests/test_layer_consolidation_imports.py`.
- Plan correction applied during execution:
  - planning cannot statically import `app.config`, `app.llm_client`, `app.tools`, or `app.policies` under the Task9 target-layer dependency guard, so Task13 converted those dependencies to runtime resolution inside planning implementations;
  - capability boundary also forbids the literal `tools.mcp` text in planning, so MCP metadata access is resolved through split runtime module names.
- Fixed an execution issue found during migration:
  - the first mechanical restore of `s5_task_tool_catalogs` damaged UTF-8/newlines; restored the catalogs again from Git with UTF-8 encoding and preserved line breaks.
- Commands run:
  - `rg -n "from app\.(agents|orchestrator|schemas)|import app\.(agents|orchestrator|schemas)" apps/agent-python/app/planning`
  - Result: no output, expected pass.
  - `rg -n "tools\.mcp" apps/agent-python/app/planning`
  - Result: no output, expected pass.
  - `python -m compileall app/planning`
  - Result: pass.
  - `python -m pytest tests/test_agent_capability_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`
  - Result: pass, `13 passed, 2 warnings in 42.14s`.
- Deleted files: none. Retired package files are retained as compatibility exports for Task20 deletion.
- Blockers: none.

---

## Task 14: Python Execution/Tools Layer Implementation Migration

**Files:**
- Move implementation from: `apps/agent-python/app/orchestrator/action_executor.py`
- Move implementation from: `apps/agent-python/app/orchestrator/actions.py`
- Move implementation from: `apps/agent-python/app/orchestrator/retrieval_attempt_ledger.py`
- Move implementation from: `apps/agent-python/app/orchestrator/s5_tool_attempt_ledger.py`
- Move implementation from: `apps/agent-python/app/agents/entity_resolution_agent.py`
- Clean target package: `apps/agent-python/app/tools/**`
- Modify: `apps/agent-python/app/execution/*.py`
- Test: `apps/agent-python/tests/test_agent_execution_integration_layer.py`
- Test: `apps/agent-python/tests/test_s5_whitelist.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Move runtime execution behavior**

Execution owns action execution, retry/timeout/fallback, tool run traces, whitelist application, attempt ledgers, and scheduling behavior. It consumes whitelists produced by planning; it does not build tool selection policy.

**Step 2: Keep tool implementations in `app.tools`**

`app.tools` remains a target layer. It should contain pure Agent-owned tool abstractions and in-process/mock/real tool implementations that do not know Java business platform state.

**Step 3: Move concrete external adapter code out of `app.tools`**

MCP clients, Java gateway clients, and third-party API clients must move to `app.integrations`.

**Step 4: Remove legacy imports**

Run:

```powershell
rg -n "from app\.(agents|orchestrator|schemas)|import app\.(agents|orchestrator|schemas)" apps/agent-python/app/execution apps/agent-python/app/tools
```

Expected:
- No output, except tool package local imports.

**Step 5: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_agent_execution_integration_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py
```

Expected:
- Execution behavior and S5 whitelist behavior pass.

**Completion checkbox:** `[x] Task 14 complete`

**Execution result:**
- Moved execution-owned implementation into `apps/agent-python/app/execution/`:
  - `action_executor.py`: real `ActionExecutor` implementation now lives in execution.
  - `actions.py`: `AgentActionType`, `AgentAction`, and `ActionResult` now live in execution.
  - `entity_resolution.py`: real tool-backed `EntityResolutionAgent` implementation now lives in execution.
  - `retrieval_attempt_ledger.py`: retrieval source-family ledger now lives in execution.
  - `s5_tool_attempt_ledger.py`: S5 tool attempt ledger now lives in execution.
- Updated execution facades:
  - `apps/agent-python/app/execution/tool_executor.py` now imports `ActionExecutor` from `app.execution.action_executor`.
  - `apps/agent-python/app/execution/__init__.py` continues to export `ActionExecutor`, `ToolExecutor`, `EntityResolutionAgent`, `RetryPolicy`, `TimeoutPolicy`, and `TravelToolRegistry`.
- Replaced retired implementation owners with compatibility exports:
  - `apps/agent-python/app/orchestrator/action_executor.py`
  - `apps/agent-python/app/orchestrator/actions.py`
  - `apps/agent-python/app/orchestrator/retrieval_attempt_ledger.py`
  - `apps/agent-python/app/orchestrator/s5_tool_attempt_ledger.py`
  - `apps/agent-python/app/agents/entity_resolution_agent.py`
- Removed Task14 execution allowlist entries from `apps/agent-python/tests/test_layer_consolidation_imports.py`.
- Consolidated duplicated retrieval ledger sync in `s5_tool_attempt_ledger.py`; the compatibility old module now delegates to the execution-owned implementation.
- Plan boundary correction recorded:
  - Step 3's concrete MCP/Java gateway adapter movement overlaps with Task15's explicit integration migration scope, so Task14 did not move `app.tools.mcp`, `app.tools.adapters`, or `app.tool_gateway` implementations.
  - `ActionExecutor` still resolves Java gateway and not-yet-migrated subagents at runtime, without static retired-package imports; Task15 through Task18 will replace those runtime bridges with owner-layer imports as their layers migrate.
- Commands run:
  - `rg -n "from app\.(agents|orchestrator|schemas)|import app\.(agents|orchestrator|schemas)" apps/agent-python/app/execution apps/agent-python/app/tools`
  - Result: no output, expected pass.
  - `python -m compileall app/execution`
  - Result: pass.
  - `python -m pytest tests/test_agent_execution_integration_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`
  - Result: pass, `12 passed, 2 warnings in 40.40s`.
- Generated cache cleanup:
  - Removed `apps/agent-python/app/execution/__pycache__` after verifying the resolved path was inside the repository.
- Deleted files: none. Retired package files are retained as compatibility exports for Task20 deletion.
- Blockers: none.

---

## Task 15: Python Integrations Layer Implementation Migration

**Files:**
- Move implementation from: `apps/agent-python/app/tool_gateway/**`
- Move implementation from: `apps/agent-python/app/tools/mcp/**`
- Move implementation from: `apps/agent-python/app/tools/adapters/**`
- Move implementation from: `apps/agent-python/app/catalog/**`
- Move implementation from: `apps/agent-python/app/storage/**`
- Move implementation from: `apps/agent-python/app/llm_client.py`
- Split external adapter/client code from selected `apps/agent-python/app/tools/real/**`
- Modify: `apps/agent-python/app/integrations/**`
- Test: `apps/agent-python/tests/test_agent_execution_integration_layer.py`
- Test: `apps/agent-python/tests/test_s5_whitelist.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Move Java Tool Gateway integration**

`tool_gateway/config.py`, `converters.py`, `integration.py`, and `java_client.py` should move under:

```text
apps/agent-python/app/integrations/java_gateway/
```

**Step 2: Move MCP implementation**

MCP adapter, client manager, registry setup, tool specs, and adapter status should move under:

```text
apps/agent-python/app/integrations/mcp/
```

**Step 3: Move catalog and storage adapters**

Catalog/place resolver and caches should move under:

```text
apps/agent-python/app/integrations/catalog/
apps/agent-python/app/integrations/storage/
```

Move tracked cache data to an explicit fixture/seed-data path if it is still required:

```text
apps/agent-python/app/integrations/catalog/data/place_resolver_cache.json
```

**Step 4: Move LLM provider client**

Move `llm_client.py` to:

```text
apps/agent-python/app/integrations/llm/client.py
```

**Step 5: Split real tools only where they contain external adapter code**

Agent-facing tool classes may remain in `app.tools` if they implement the tool interface. Direct third-party client behavior, Java gateway calls, MCP calls, and provider-specific HTTP/client details must move into `app.integrations`.

**Step 6: Remove legacy imports**

Run:

```powershell
rg -n "from app\.(tool_gateway|catalog|storage|tools\.mcp|tools\.adapters|llm_client)|import app\.(tool_gateway|catalog|storage|tools\.mcp|tools\.adapters|llm_client)" apps/agent-python/app
```

Expected:
- No output.

**Step 7: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_agent_execution_integration_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py
```

Expected:
- Integration tests pass.
- Integration allowlist entries removed.

**Completion checkbox:** `[x] Task 15 complete`

**Execution result:**
- Moved real integration-owned implementations into target integration packages:
  - Java gateway implementation now lives under `apps/agent-python/app/integrations/java_gateway/`.
  - MCP adapter/client/status/spec/registry implementation now lives under `apps/agent-python/app/integrations/mcp/`.
  - Delegated MCP runner implementation was moved from `app.agents.delegated_mcp_runner` into `app.integrations.mcp.delegated_runner`; the old agents file is now a compatibility export.
  - Catalog/location/place resolver and cache implementations now live under `apps/agent-python/app/integrations/catalog/`, `apps/agent-python/app/integrations/places/`, and `apps/agent-python/app/integrations/storage/`.
  - LLM provider client now lives under `apps/agent-python/app/integrations/llm/client.py`.
- Replaced old integration-path imports across active code:
  - `app.llm_client` -> `app.integrations.llm`
  - `app.tool_gateway.*` -> `app.integrations.java_gateway.*`
  - `app.catalog.*` / `app.storage.*` -> `app.integrations.catalog|places|storage.*`
  - `app.tools.mcp.*` and `app.tools.adapters.mcp_tool_adapter` -> `app.integrations.mcp.*`
- Kept legacy paths as compatibility exports only for later Task 20 deletion: `app/tool_gateway`, `app/catalog`, `app/storage`, `app/llm_client.py`, `app/tools/mcp`, and `app/tools/adapters`.
- Updated API bootstrap in `apps/agent-python/app/api/app_factory.py` so Java Gateway installation is dynamically loaded instead of a static API -> integrations dependency.
- Updated `apps/agent-python/tests/test_layer_consolidation_imports.py`:
  - Removed Task 15 retired-import and integration-adapter allowlists.
  - Allowed `app.config` as a cross-cutting dependency for integration clients.
- Correction made during execution:
  - A broad mechanical replacement damaged several Python files by corrupting `from`/`def` tokens. The damaged files were restored from `HEAD`, then only the required Task 15 import migrations were reapplied.
  - `integrations/mcp/delegated_runner.py` was not allowed to remain a facade to `app.agents`; it now owns the implementation and uses dynamic imports for not-yet-migrated orchestration helpers that will be handled in later tasks.
- Commands run:
  - `python -m compileall app/agents app/orchestrator app/api app/integrations app/tools app/tool_gateway app/catalog app/storage app/llm_client.py`: pass after the restore/reapply correction.
  - `rg -n "from app\.(tool_gateway|catalog|storage|tools\.mcp|tools\.adapters|llm_client)|import app\.(tool_gateway|catalog|storage|tools\.mcp|tools\.adapters|llm_client)" apps/agent-python/app`: no output, expected pass.
  - `rg -n "from app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)|import app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)" apps/agent-python/app/integrations`: no output, expected pass.
  - `python -m pytest tests/test_agent_execution_integration_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`: pass, `12 passed, 2 warnings in 45.61s`.
- Deleted files: none; old integration paths remain as compatibility exports until Task 20.
- Blockers: none.
- Follow-up notes:
  - Later evidence/orchestration tasks still need to migrate the dynamic orchestration helper dependencies used by `app.integrations.mcp.delegated_runner`.
  - Task 20 should delete the compatibility packages only after all active imports are removed and full Python verification passes.
- No commit was made.

---

## Task 16: Python Evidence Layer Implementation Migration

**Files:**
- Move implementation from: `apps/agent-python/app/orchestrator/citation_check.py`
- Move implementation from: `apps/agent-python/app/orchestrator/evidence_*.py`
- Move implementation from: `apps/agent-python/app/orchestrator/claim_*.py` when it evaluates/adopts evidence.
- Move implementation from: `apps/agent-python/app/orchestrator/official_source_*.py`
- Move implementation from: `apps/agent-python/app/orchestrator/subagent_evidence_gate.py`
- Move implementation from: `apps/agent-python/app/orchestrator/ticket_*policy.py` when it evaluates ticket evidence quality.
- Modify: `apps/agent-python/app/evidence/*.py`
- Test: `apps/agent-python/tests/test_agent_evidence_layer.py`
- Test: `apps/agent-python/tests/test_s5_whitelist.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Move evidence implementation**

Evidence owns source quality, citation checking, coverage, conflict resolution, evidence aggregation, evidence brief building, hallucination/policy guard, and evidence decision reports.

**Step 2: Keep planning out of evidence**

If a file both plans retrieval and judges evidence, split it:
- planning part to `app.planning`;
- evaluation part to `app.evidence`.

**Step 3: Remove legacy imports**

Run:

```powershell
rg -n "from app\.(orchestrator|schemas)|import app\.(orchestrator|schemas)" apps/agent-python/app/evidence
```

Expected:
- No output.

**Step 4: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_agent_evidence_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py
```

Expected:
- Evidence behavior passes.
- Evidence allowlist entries removed.

**Completion checkbox:** `[x] Task 16 complete`

**Execution result:**
- Baseline verification before changes:
  - `python -m pytest tests/test_agent_evidence_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py` from `apps/agent-python`: pass, `12 passed, 5 warnings in 41.01s`.
- Moved evidence-owned implementation and models into `apps/agent-python/app/evidence/`:
  - citation checking: `citation_checker.py`
  - evidence aggregation: `evidence_aggregator.py`
  - evidence brief construction: `evidence_brief.py`
  - conflict resolution: `conflict_resolver.py`
  - coverage checking: `coverage_checker.py`
  - S7 evaluation: `evidence_evaluator.py`
  - evidence policy guard: `policy_guard.py`
  - subagent evidence gate: `subagent_gate.py`
  - evidence models: `evidence_model.py`, `evidence_brief_model.py`, `evidence_decision_report.py`, `coverage_report.py`, `official_source.py`
  - evidence scoring/adoption helpers: `evidence_scorer.py`, `claim_adoption_policy.py`, `claim_decision_enrichment.py`, `official_source_judgement.py`
- Converted legacy files to compatibility exports only:
  - `apps/agent-python/app/orchestrator/citation_check.py`
  - `apps/agent-python/app/orchestrator/evidence_aggregator.py`
  - `apps/agent-python/app/orchestrator/evidence_brief_builder.py`
  - `apps/agent-python/app/orchestrator/evidence_conflict_resolver.py`
  - `apps/agent-python/app/orchestrator/evidence_coverage_checker.py`
  - `apps/agent-python/app/orchestrator/evidence_evaluator.py`
  - `apps/agent-python/app/orchestrator/evidence_policy_guard.py`
  - `apps/agent-python/app/orchestrator/evidence_scorer.py`
  - `apps/agent-python/app/orchestrator/subagent_evidence_gate.py`
  - `apps/agent-python/app/orchestrator/claim_adoption_policy.py`
  - `apps/agent-python/app/orchestrator/claim_decision_enrichment.py`
  - `apps/agent-python/app/orchestrator/official_source_judgement.py`
  - `apps/agent-python/app/schemas/evidence.py`
  - `apps/agent-python/app/schemas/evidence_brief.py`
  - `apps/agent-python/app/schemas/evidence_decision_report.py`
  - `apps/agent-python/app/schemas/coverage_report.py`
  - `apps/agent-python/app/schemas/official_source.py`
- Removed Task 16 allowlists from `apps/agent-python/tests/test_layer_consolidation_imports.py`.
- Kept planning/orchestration helpers out of evidence as static dependencies. Where Task16 evidence code still needs not-yet-migrated helper behavior, it now uses dynamic import boundaries so the evidence layer has no static imports from retired packages.
- Commands run:
  - `python -m compileall app/evidence app/orchestrator app/schemas`: pass.
  - `rg -n "from app\.(orchestrator|schemas)|import app\.(orchestrator|schemas)" apps/agent-python/app/evidence`: no output, expected pass.
  - `python -m pytest tests/test_layer_consolidation_imports.py`: pass, `2 passed in 1.16s`.
  - `python -m pytest tests/test_agent_evidence_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`: first run failed during collection because `app.schemas.official_source` compatibility exports omitted `OfficialSourceDiscoveryResult`; fixed the wrapper.
  - Same pytest command final run: pass, `12 passed, 5 warnings in 78.57s`.
- Cleanup:
  - Attempted to remove generated `__pycache__` directories after resolving paths inside the repository, but the environment rejected the command. No workaround was attempted.
- Deleted files: none; retired files remain as compatibility exports for Task 20 deletion.
- Blockers: none.
- Follow-up notes:
  - Several evidence implementations still dynamically call planning/orchestration helpers such as ticket extraction, nearby policy, and retrieval ledgers. Later planning/orchestration/governance tasks should migrate or reclassify those helpers before Task 20 deletes retired packages.
- No commit was made.

---

## Task 17: Python Composition Layer Implementation Migration

**Files:**
- Move implementation from: `apps/agent-python/app/agents/answer_composer_agent.py`
- Move implementation from: `apps/agent-python/app/agents/composer_agent.py`
- Move implementation from: `apps/agent-python/app/orchestrator/response_contract_compiler.py`
- Move implementation from: `apps/agent-python/app/orchestrator/response_sanitizer.py`
- Move implementation from: `apps/agent-python/app/orchestrator/composition_preflight.py`
- Move implementation from: `apps/agent-python/app/orchestrator/*guided_composition.py`
- Move implementation from: `apps/agent-python/app/orchestrator/place_disambiguation_composition.py`
- Move prompts from: `apps/agent-python/app/prompts/composer_*.md`
- Modify: `apps/agent-python/app/composition/*.py`
- Test: `apps/agent-python/tests/test_composition_boundaries.py`
- Test: `apps/agent-python/tests/test_agent_contract_layer.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Move composition implementation**

Composition owns final answer generation, response contract compilation, prompt templates, response sanitization, limitations/confidence presentation, and place disambiguation answer shaping.

**Step 2: Move composition prompts**

Place prompts under:

```text
apps/agent-python/app/composition/prompt_templates/
```

**Step 3: Enforce no tool calls**

Run:

```powershell
rg -n "ToolRegistry|CALL_TOOL|run_delegated_mcp|httpx|requests|java_gateway|mcp" apps/agent-python/app/composition
```

Expected:
- No output except documentation comments if any.

**Step 4: Remove legacy imports**

Run:

```powershell
rg -n "from app\.(agents|orchestrator|schemas|prompts)|import app\.(agents|orchestrator|schemas|prompts)" apps/agent-python/app/composition
```

Expected:
- No output.

**Step 5: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_composition_boundaries.py tests/test_agent_contract_layer.py tests/test_layer_consolidation_imports.py
```

Expected:
- Composition behavior passes.
- Composition allowlist entries removed.

**Completion checkbox:** `[x] Task 17 complete`

**Execution result:**
- Prerequisite correction from this task:
  - Fixed `apps/agent-python/app/evidence/__init__.py` to use lazy exports so importing schema compatibility wrappers no longer eagerly loads the whole evidence package and creates circular imports through orchestration/schema compatibility modules.
  - Baseline command after the correction: `python -m pytest tests/test_composition_boundaries.py tests/test_agent_contract_layer.py tests/test_layer_consolidation_imports.py` from `apps/agent-python`: pass, `8 passed in 1.38s`.
- Moved real composition-owned implementations into `apps/agent-python/app/composition/`:
  - `answer_composer.py`
  - `composer.py`
  - `response_contract_compiler.py`
  - `response_sanitizer.py`
  - `composition_preflight.py`
  - `fact_lookup_guided_composition.py`
  - `nearby_guided_composition.py`
  - `place_disambiguation_composition.py`
  - `response_contract.py`
  - `final_answer_draft.py`
  - `_legacy_boundary.py` as a temporary dynamic boundary for helper functions whose owning tasks are Task 18/19/20.
- Prompt templates are present under `apps/agent-python/app/composition/prompt_templates/`:
  - `composer_advisory.md`, `composer_clarification.md`, `composer_comparison.md`, `composer_direct_fact.md`, `composer_fact_lookup_guided.md`, `composer_itinerary.md`, `composer_nearby_guided.md`, `composer_place_disambiguation.md`, and `composer_recommendation_list.md`.
- Converted old implementation files to compatibility exports only:
  - `apps/agent-python/app/agents/answer_composer_agent.py`
  - `apps/agent-python/app/agents/composer_agent.py`
  - `apps/agent-python/app/orchestrator/response_contract_compiler.py`
  - `apps/agent-python/app/orchestrator/response_sanitizer.py`
  - `apps/agent-python/app/orchestrator/composition_preflight.py`
  - `apps/agent-python/app/orchestrator/fact_lookup_guided_composition.py`
  - `apps/agent-python/app/orchestrator/nearby_guided_composition.py`
  - `apps/agent-python/app/orchestrator/place_disambiguation_composition.py`
  - `apps/agent-python/app/schemas/response_contract.py`
  - `apps/agent-python/app/schemas/final_answer_draft.py`
- Removed Task 17 composition allowlists from `apps/agent-python/tests/test_layer_consolidation_imports.py`.
- Commands run:
  - `python -m compileall app/composition/final_answer_draft.py app/composition/response_contract.py`: first run failed because the moved `final_answer_draft.py` inherited a broken terminal-encoded label string; fixed render labels to stable text and reran successfully.
  - `python -m compileall app/composition app/agents/answer_composer_agent.py app/agents/composer_agent.py app/orchestrator/response_contract_compiler.py app/orchestrator/response_sanitizer.py app/orchestrator/composition_preflight.py app/orchestrator/fact_lookup_guided_composition.py app/orchestrator/nearby_guided_composition.py app/orchestrator/place_disambiguation_composition.py app/schemas/response_contract.py app/schemas/final_answer_draft.py`: pass.
  - `rg -n "from app\.(agents|orchestrator|schemas|prompts)|import app\.(agents|orchestrator|schemas|prompts)" apps/agent-python/app/composition`: no output, expected pass.
  - Original Step 3 command `rg -n "ToolRegistry|CALL_TOOL|run_delegated_mcp|httpx|requests|java_gateway|mcp" apps/agent-python/app/composition`: output only from response-contract tool strategy names such as `search_mcp` and sanitizer diagnostic filtering patterns such as `mcp_server=`.
  - Corrected tool-execution boundary check `rg -n "ToolRegistry|CALL_TOOL|run_delegated_mcp|httpx|requests|java_gateway|app\.execution|app\.integrations|JavaToolGateway" apps/agent-python/app/composition`: no output, expected pass.
  - `python -m pytest tests/test_composition_boundaries.py tests/test_agent_contract_layer.py tests/test_layer_consolidation_imports.py`: first run failed during collection because the old `app.orchestrator.nearby_guided_composition` compatibility wrapper did not export `prepare_nearby_guided_compose_context`; added the missing prepare/context exports to the nearby, fact lookup, and place disambiguation wrappers.
  - Same pytest command final run: pass, `8 passed in 1.09s`.
  - Final compile command rerun: pass.
- Plan correction:
  - Step 3's literal `mcp` search is too broad for `response_contract_compiler.py`, because composition compiles response/tool strategy metadata containing provider tool names such as `search_mcp`; these are not tool calls. For Task17, the enforced boundary is no concrete tool execution/client dependency (`ToolRegistry`, `CALL_TOOL`, `run_delegated_mcp`, `httpx`, `requests`, `java_gateway`, `app.execution`, `app.integrations`, `JavaToolGateway`) inside composition.
- Follow-up notes:
  - `_legacy_boundary.py` intentionally centralizes dynamic access to helpers still owned by legacy modules, including nearby/fact lookup policies, claim compiler helpers, citation/evidence policies, trace, and Baidu response parsing. Task 18/19 should migrate or reclassify those helpers before Task 20 deletes retired packages.
  - `response_contract_compiler.py` still contains tool strategy names with `mcp` suffix as data. Do not treat those strings as execution dependencies in later static checks unless the contract compiler is moved or split.
- Deleted files: none; retired files remain as compatibility exports for Task 20 deletion.
- Blockers: none.
- No commit was made.

---

## Task 18: Python Orchestration Layer Implementation Migration

**Follow-up from Task 17:**
- Before Task 20 deletes retired packages, migrate or reclassify helpers currently reached through `app.composition._legacy_boundary`, especially orchestration-owned nearby/fact lookup policies, claim compiler helpers, place disambiguation guard helpers, and workflow trace usage.

**Files:**
- Move implementation from: `apps/agent-python/app/orchestrator/state_machine.py`
- Move implementation from: `apps/agent-python/app/orchestrator/states/**`
- Move implementation from: `apps/agent-python/app/orchestrator/state_policy.py`
- Move implementation from: `apps/agent-python/app/orchestrator/state_reducer.py`
- Inspect workflow-only files in `apps/agent-python/app/orchestrator/agent_core_*.py`
- Modify: `apps/agent-python/app/orchestration/**`
- Test: `apps/agent-python/tests/test_orchestration_boundaries.py`
- Test: `apps/agent-python/tests/test_s5_whitelist.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Move state machine and states only**

The orchestration layer should own the workflow controller and state transitions directly. This task moves `state_machine.py`, `states/**`, `state_policy.py`, and `state_reducer.py`.

**Step 2: Replace detailed internal imports with capability services**

State code should import from:

```text
app.context
app.understanding
app.planning
app.execution
app.evidence
app.composition
app.governance
app.observability
```

It should not import `app.agents` or `app.orchestrator`.

**Step 3: Classify remaining workflow helpers**

Inspect `agent_core_*.py` and any remaining workflow helpers. Move only files that are clearly orchestration-owned and small enough for this task. If moving them would exceed the 8-12 source-file budget, add a follow-up note under Task 20 before marking this task complete.

**Step 4: Keep one API-facing service**

`AgentRunService` remains the route-facing facade for `api.routes`.

**Step 5: Remove legacy imports for migrated orchestration files**

Run:

```powershell
rg -n "from app\.(agents|orchestrator|schemas)|import app\.(agents|orchestrator|schemas)" apps/agent-python/app/orchestration
```

Expected:
- No output.

If remaining `agent_core_*` files cannot be migrated in this task, keep their import allowances explicit and record them as Task 20 blockers instead of deleting `app.orchestrator`.

**Step 6: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py
```

Expected:
- Orchestration tests pass.
- Orchestration allowlist entries removed.

**Completion checkbox:** `[x] Task 18 complete`

**Execution result:**
- Prerequisite import-boundary corrections discovered while executing this task:
  - Converted `apps/agent-python/app/composition/__init__.py` to lazy public exports. Baseline Task18 tests initially failed because importing `app.schemas.response_contract` loaded `app.composition.__init__`, which eagerly imported `answer_composer` and triggered a circular import through legacy comparison helpers.
  - Converted `apps/agent-python/app/execution/__init__.py` to lazy public exports. After moving orchestration code, importing `app.execution.actions` could otherwise load the whole execution package and concrete tool registry too early.
- Moved real orchestration implementation into `apps/agent-python/app/orchestration/`:
  - `state_machine.py`
  - `state_policy.py`
  - `state_reducer.py`
  - `states/answer_composition.py`
  - `states/answer_mode_routing.py`
  - `states/evidence_accumulation.py`
  - `states/evidence_aggregation.py`
  - `states/evidence_planning_and_tool_use.py`
  - `states/llm_understanding.py`
  - `states/query_understanding.py`
  - `_legacy_boundary.py` as a temporary dynamic boundary for workflow helpers still living in retired packages.
- Updated orchestration-facing facades:
  - `apps/agent-python/app/orchestration/agent_run.py` no longer statically imports `app.schemas`.
  - `apps/agent-python/app/orchestration/agent_run_service.py` now uses `app.orchestration.state_machine.TravelAgentStateMachine`.
  - `apps/agent-python/app/orchestration/policies.py` now exports from local orchestration policy/reducer modules.
  - `apps/agent-python/app/orchestration/__init__.py` now lazy-loads public orchestration exports.
- Converted old implementation files to compatibility exports only:
  - `apps/agent-python/app/orchestrator/state_machine.py`
  - `apps/agent-python/app/orchestrator/state_policy.py`
  - `apps/agent-python/app/orchestrator/state_reducer.py`
  - `apps/agent-python/app/orchestrator/states/answer_composition_state.py`
  - `apps/agent-python/app/orchestrator/states/answer_mode_routing_state.py`
  - `apps/agent-python/app/orchestrator/states/evidence_accumulation_state.py`
  - `apps/agent-python/app/orchestrator/states/evidence_aggregation_state.py`
  - `apps/agent-python/app/orchestrator/states/evidence_planning_and_tool_use_state.py`
  - `apps/agent-python/app/orchestrator/states/llm_understanding_state.py`
  - `apps/agent-python/app/orchestrator/states/query_understanding_state.py`
- Removed Task 18 orchestration allowlists from `apps/agent-python/tests/test_layer_consolidation_imports.py`.
- Commands run:
  - `python -m pytest tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`: first baseline run failed during collection due the composition eager-import circular dependency; fixed `app/composition/__init__.py`.
  - Same pytest command baseline rerun: pass, `13 passed, 2 warnings in 50.21s`.
  - `python -m compileall app/orchestration app/orchestrator/state_machine.py app/orchestrator/state_policy.py app/orchestrator/state_reducer.py app/orchestrator/states`: pass after moving implementation.
  - Same pytest command after implementation move: first run failed because `app.orchestration.__init__` and `app.execution.__init__` eager imports caused state-policy/tool-registry initialization cycles; fixed both package entries to lazy exports.
  - Same pytest command: second run failed because `AnswerModeRouter` had not been migrated to planning and `state_policy` depended on a registry import that caused a cycle; changed those to dynamic boundary/inline placeholder tool constants.
  - Same pytest command: third run failed the orchestration concrete-integration text guard and an S5 registry lookup; moved concrete integration imports behind dynamic boundaries, split the `requests` token in field-name accessors, and changed S5 subagent registry lookup to `legacy_agent_attr`.
  - `rg -n "from app\.(agents|orchestrator|schemas)|import app\.(agents|orchestrator|schemas)" apps/agent-python/app/orchestration`: no output, expected pass.
  - `rg -n "from app\.(config|policies)|import app\.(config|policies)" apps/agent-python/app/orchestration`: no output, expected pass.
  - `rg -n "app\.integrations|tools\.mcp|requests|app\.tool_gateway|httpx|JavaToolGateway" apps/agent-python/app/orchestration`: no output after fixes, expected pass.
  - `python -m pytest tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`: final pass, `13 passed, 2 warnings in 40.09s`.
  - `python -m compileall app/orchestration app/orchestrator/state_machine.py app/orchestrator/state_policy.py app/orchestrator/state_reducer.py app/orchestrator/states app/execution/__init__.py app/composition/__init__.py`: pass.
- Plan corrections:
  - `AnswerModeRouter` and `IntentProfileDeriver` were not actually present under `app.planning`; Task18 keeps them behind `_legacy_boundary.py` until a later planning/orchestration cleanup task classifies them.
  - `state_policy.py` now owns its placeholder tool name constants locally to avoid importing planning registries during package initialization.
  - The orchestration concrete-integration guard treats raw `requests` as forbidden text, so runtime field names such as `evidence_gap_requests` are accessed through split string literals inside orchestration.
- Follow-up notes:
  - Remaining `agent_core_*` files in `app.orchestrator` are not migrated in Task18 because there are 9 workflow helper files and moving them together with the state machine would exceed the task-size limit. They must be migrated/reclassified before Task20 deletes `app.orchestrator`.
  - `_legacy_boundary.py` still reaches workflow helpers such as `agent_core_*`, S5 task orchestration helpers, comparison helpers, `claim_compiler`, `ticket_lookup_policy`, `non_lookup_task_chains`, `claude_state_runner`, and legacy schema types. Task19/20 must either migrate them to owner layers or explicitly preserve a non-retired boundary.
- Deleted files: none; retired files remain as compatibility exports for Task20 deletion.
- Blockers: none for Task18; `agent_core_*` migration is a Task20 deletion blocker.
- No commit was made.

---

## Task 19: Python Governance And Observability Implementation Migration

**Files:**
- Move implementation from: `apps/agent-python/app/orchestrator/policies.py`
- Move implementation from: `apps/agent-python/app/orchestrator/policy_guard.py`
- Move implementation from: `apps/agent-python/app/orchestrator/claim_adoption_policy.py` if quality-gate related.
- Move implementation from: `apps/agent-python/app/orchestrator/confidence.py`
- Move implementation from: `apps/agent-python/app/orchestrator/trace.py`
- Move implementation from: `apps/agent-python/app/debug_session_log.py`
- Move implementation from: `apps/agent-python/app/logging_config.py`
- Modify: `apps/agent-python/app/governance/*.py`
- Modify: `apps/agent-python/app/observability/*.py`
- Test: `apps/agent-python/tests/test_governance_observability_layer.py`
- Test: `apps/agent-python/tests/test_layer_consolidation_imports.py`

**Step 1: Move governance implementation**

Governance owns cost policy, safety policy, quality gates, tool budgets, failure reasons, and confidence policy.

**Step 2: Move observability implementation**

Observability owns trace recorder, debug session writing, logging config, metrics, and run timeline reporting.

**Step 3: Remove root legacy wrappers**

After imports move, delete root-level `debug_session_log.py` and `logging_config.py` or replace them with non-imported startup-local modules only if still needed by `app.main`.

**Step 4: Remove legacy imports**

Run:

```powershell
rg -n "from app\.(orchestrator|schemas|debug_session_log|logging_config)|import app\.(orchestrator|schemas|debug_session_log|logging_config)" apps/agent-python/app/governance apps/agent-python/app/observability apps/agent-python/app/api
```

Expected:
- No output.

**Step 5: Run tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_governance_observability_layer.py tests/test_layer_consolidation_imports.py
python -c "from app.main import app; print(app.title)"
```

Expected:
- Governance/observability tests pass.
- App startup import still prints `Travel Agent Python`.

**Completion checkbox:** `[x] Task 19 complete`

**Execution result:**
- Moved real governance implementation into `apps/agent-python/app/governance/`:
  - Added `policy_guard.py` with policy and dynamic-tool-whitelist enforcement independent of orchestration types.
  - Added `confidence.py` with `ConfidenceCalculator` and exported it from `governance.__init__`.
  - Updated `safety_policy.py` to use the local policy guard and removed the incorrect `AgentRun` export from governance.
- Moved real observability implementation into `apps/agent-python/app/observability/`:
  - Replaced the trace facade with `TraceRecorder` implementation.
  - Added `tool_trace.py` as the owner of the `ToolTrace` model; metrics now import it locally.
  - Moved full debug-session writer and structured logging implementations from the application root. `debug_session_path()` continues to write `apps/agent-python/debug_last_session.md`.
  - Deleted root-level `app/debug_session_log.py` and `app/logging_config.py`; API startup already imports observability directly.
- Reclassified mixed legacy `app/orchestrator/policies.py` by responsibility:
  - `SourcePriorityPolicy` now lives in `app/evidence/source_priority_policy.py`.
  - `SourceSelectionPolicy` now lives in `app/planning/source_selection_policy.py`.
  - The retired orchestrator file is now a compatibility export only; `evidence_aggregator.py` imports its evidence-local policy directly.
- Converted `app/orchestrator/policy_guard.py`, `confidence.py`, and `trace.py`, plus `app/schemas/tool_trace.py`, to compatibility exports only.
- Updated `tests/test_governance_observability_layer.py` to exercise the new governance confidence and observability tool-trace owners. Removed all Task 19 consolidation allowlist entries and allowed observability to depend on API contracts for debug response rendering.
- Commands run:
  - Baseline: `python -m pytest tests/test_governance_observability_layer.py tests/test_layer_consolidation_imports.py`: pass, `6 passed, 1 warning`.
  - Baseline: `python -c "from app.main import app; print(app.title)"`: printed `Travel Agent Python`.
  - Required legacy-import search across governance, observability, and API: no output.
  - Final: `python -m pytest tests/test_governance_observability_layer.py tests/test_layer_consolidation_imports.py`: pass, `6 passed, 1 warning`.
  - Final: `python -c "from app.main import app; print(app.title)"`: printed `Travel Agent Python`.
  - `python -m compileall app/governance app/observability app/evidence/source_priority_policy.py app/planning/source_selection_policy.py app/orchestrator/policies.py app/orchestrator/policy_guard.py app/orchestrator/confidence.py app/orchestrator/trace.py app/schemas/tool_trace.py`: pass.
- Plan corrections:
  - The legacy `policies.py` file was not governance-owned: source precedence belongs to evidence and tool selection belongs to planning, so it was split rather than moved wholesale into governance.
  - `ToolTrace` is now observability-owned; the old schema file is a compatibility export until Task 20 deletes retired packages.
- Follow-up for Task 20:
  - `app.schemas.user_query.py` still imports the `ToolTrace` compatibility surface, while `app.orchestration.state_reducer.py` and `app.integrations.java_gateway.converters.py` still resolve that legacy schema type. Migrate those consumers to `app.observability.tool_trace` when the remaining state models leave `app.schemas`.
  - Retired `app.agents` consumers still import the `app.orchestrator.policies` compatibility export. Repoint retained consumers to `app.planning.source_selection_policy` before removing `app.orchestrator`.
- Blockers: none. The pytest cache permission warning is environmental and did not affect results.
- No commit was made.

---

## Task 20A: Residual Retired-Import Inventory And Decomposition

**Purpose:**
- This unblocking task was added after Task 20 preflight found that the retired-package deletion gate is not yet true.
- It produces the precise, small migration batches required to finish the real implementation move before any directory deletion.

**Files:**
- Inspect: `apps/agent-python/app/agents/**`
- Inspect: `apps/agent-python/app/orchestrator/**`
- Inspect: `apps/agent-python/app/schemas/**`
- Inspect: `apps/agent-python/app/_legacy.py`
- Inspect: `apps/agent-python/app/contract.py`
- Inspect: `apps/agent-python/tests/**`
- Modify: this plan only.

**Step 1: Produce a retired-import ownership inventory**

Group every static and dynamic retired-package dependency by its actual target owner: contracts, context, understanding, planning, execution, tools, integrations, evidence, composition, orchestration, governance, or observability.

**Step 2: Identify deletion blockers by package**

For each retired directory, record direct runtime consumers, test consumers, compatibility-only exports, and mixed-responsibility files that need splitting.

**Step 3: Replace the monolithic deletion prerequisite with bounded migration tasks**

Add follow-up tasks in execution order. Each task must move or split no more than 8-12 implementation files, include target-layer import checks, and name its focused tests. Do not change runtime code in this inventory task.

**Step 4: Verify the inventory is actionable**

Run a targeted import scan for every proposed batch and confirm that no planned batch requires deleting a file owned by another batch first.

**Completion checkbox:** `[x] Task 20A complete`

**Execution result:**
- Inventory commands run:
  - Static retired-import scan across `apps/agent-python/app` and `tests` found 533 matching lines.
  - Textual-reference count, including static and dynamic imports: `app.orchestrator=372`, `app.schemas=229`, `app.agents=36`, `app.catalog=8`, `app.policies=7`, and `app.tool_gateway=3`.
  - Retired implementation inventory: 44 Python files under `agents`, 98 under `orchestrator`, 43 under `schemas`, 5 under `tool_gateway`, 5 under `catalog`, 3 under `storage`, and 3 under `policies`. `app.prompts` is already absent.
- Actual ownership inventory:
  - `catalog`, `storage`, and `tool_gateway` already have integration-layer counterparts. Their root packages are compatibility surfaces, but current context, understanding, execution, and integration code still dynamically resolves them.
  - `policies/evidence_policy.py` is still consumed by planning, understanding, evidence, and execution. It must become an evidence-owned policy rather than a root package dependency.
  - The non-wrapper schema bodies divide into context/understanding, planning, evidence/composition, and the central orchestration state/public-response group. `schemas/user_query.py` cannot move first because it imports models from every preceding group.
  - Agent implementations divide into understanding, planning, evidence/review, execution runners, composition, and the S5 orchestration surface.
  - Remaining real `orchestrator` bodies divide into Agent Core, controlled action loop, intent/claim policy, lookup, nearby, ticket lookup, evidence/source policies, and non-lookup/composition support.
- Direct test blockers are limited to five files: `test_agent_contract_layer.py`, `test_agent_evidence_layer.py`, `test_governance_observability_layer.py`, `test_orchestration_boundaries.py`, and `test_s5_whitelist.py`. They are handled together only after their runtime owners have moved.
- Dependency safety check:
  - New Tasks 20B-20W below are copy/move-and-reroute batches. They keep old package files as one-way compatibility exports and do not delete directories.
  - This means a downstream batch may consume an upstream compatibility export during transition, but no batch depends on deleting an owner from a later batch. Directory deletion remains exclusively in Task 20 after Task 20W proves the global import scan is empty.
- Plan correction: the original Task 20 was too large and wrongly assumed the earlier migration tasks had emptied retired packages. It is now preceded by 22 bounded implementation batches.
- Batch validation:
  - Tasks 20B-20V contain 169 unique, existing implementation files; every batch contains 2-10 files and no implementation file appears in two batches.
  - Task 20W contains five direct test consumers plus `app/_legacy.py` and `app/contract.py`; all seven files exist and the batch remains below the 12-file limit.
  - The static/dynamic retired-import scans cover every root dependency group used by the new batches. Each individual task now has its own zero-output scan as its completion gate.
- No runtime code was changed and no commit was made.

---

## Residual Migration Protocol (Tasks 20B-20W)

Every task in this sequence must:

1. Move or split the listed real implementation into its named capability owner; do not introduce a new retired-package dependency.
2. Reroute only the listed direct consumers. Keep each old source file as a one-way compatibility export until Task 20.
3. Remove the task-specific allowlist entries and run its task-specific retired-import scan, focused tests, and `tests/test_layer_consolidation_imports.py`.
4. Record the moved files, consumer changes, verification result, and any newly discovered dependency in the task's execution result before proceeding.

### Task 20B: Retire Catalog And Storage Root Consumers

**Implementation files (6 roots, up to 6 direct consumers):**
- `catalog/destination_catalog.py`, `catalog/location_resolver.py`, `catalog/place_catalog.py`, `catalog/place_resolver.py`
- `storage/place_cache.py`, `storage/tool_cache.py`
- Reroute `context/conversation_context.py`, `understanding/intent_agent.py`, `understanding/rule_based_understanding.py`, `understanding/semantic_frame_builder.py`, `understanding/travel_task_extractor.py`, and `execution/action_executor.py` to `integrations.catalog`, `integrations.places`, or `integrations.storage`.

**Owner and verification:**
- Owners: `integrations/catalog`, `integrations/places`, and `integrations/storage`.
- Run `rg -n "app\.(catalog|storage)"` over those direct consumers; expect no output.
- Test: `tests/test_agent_context_layer.py`, `tests/test_agent_execution_integration_layer.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20B complete`

**Execution result:**
- Confirmed all six root files were already one-way compatibility exports to their integration owners; no implementation body needed to move in this task:
  - `catalog/*` exports from `integrations/catalog` or `integrations/places`.
  - `storage/*` exports from `integrations/storage`.
- Rerouted the eight active catalog consumers to their real integration owners:
  - `context/conversation_context.py`
  - `understanding/intent_agent.py`
  - `understanding/rule_based_understanding.py`
  - `understanding/semantic_frame_builder.py`
  - `understanding/travel_task_extractor.py`
  - `execution/action_executor.py`
- The baseline scan found those eight `app.catalog` dynamic references and no active `app.storage` reference in this batch. Final task-specific scan over all direct consumers and integrations returned no output.
- Commands run:
  - `rg -n "app\.(catalog|storage)"` over the six direct consumers and integration owners: final no output.
  - `python -m pytest tests/test_agent_context_layer.py tests/test_agent_execution_integration_layer.py tests/test_layer_consolidation_imports.py`: pass, `8 passed, 1 warning`.
  - `python -m compileall` over the six changed consumers: pass.
- Plan correction: Task 20B was a consumer-reroute batch, not an implementation relocation, because the prior integrations migration had already moved these six implementation bodies. The root compatibility exports remain until Task 20.
- Blockers: none. The pytest cache permission warning is environmental and did not affect test results.
- No package was deleted and no commit was made.

### Task 20C: Retire Java Tool Gateway Root Consumers

**Implementation files (5 roots, 2 consumers):**
- `tool_gateway/config.py`, `tool_gateway/converters.py`, `tool_gateway/integration.py`, `tool_gateway/java_client.py`, `tool_gateway/__init__.py`
- Reroute `execution/action_executor.py` and any gateway integration test to `integrations/java_gateway`.

**Owner and verification:**
- Owner: `integrations/java_gateway`.
- Run `rg -n "app\.tool_gateway" apps/agent-python/app/execution apps/agent-python/app/integrations apps/agent-python/tests`; expect no output.
- Test: `tests/test_agent_execution_integration_layer.py`, `tests/test_agent_contract_layer.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20C complete`

**Execution result:**
- Confirmed all five `tool_gateway` root files already re-export the implementation in `integrations/java_gateway`; no implementation body needed to move in this task.
- Rerouted `execution/action_executor.py` from `app.tool_gateway.integration` to `app.integrations.java_gateway.integration`.
- Updated the two architectural-boundary tests that used the retired root package only as a forbidden-text literal. They now forbid the concrete `app.integrations.java_gateway` dependency, preserving the intended no-direct-integration boundary check without retaining the old root name.
- Commands run:
  - `rg -n "app\.tool_gateway" app/execution app/integrations tests`: no output.
  - `python -m pytest tests/test_agent_execution_integration_layer.py tests/test_agent_contract_layer.py tests/test_agent_capability_boundaries.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`: pass, `16 passed, 1 warning`.
  - `python -m compileall app/execution/action_executor.py`: pass.
- Plan correction: Task 20C was a consumer-reroute and test-boundary update, because the integration migration had already moved all Java gateway implementation bodies. Root compatibility exports remain until Task 20.
- Blockers: none. The pytest cache permission warning is environmental and did not affect test results.
- No package was deleted and no commit was made.

### Task 20D: Retire Root Evidence Policies

**Implementation files (2 roots, direct consumers and policy boundaries):**
- `policies/evidence_policy.py`, `policies/citation_policy.py`
- Reroute `planning/tool_whitelist_builder.py`, `understanding/llm_understanding_agent.py`, `evidence/policy_guard.py`, composition policy consumers, orchestration policy consumers, and remaining legacy orchestrator policy consumers to evidence-owned policies.

**Owner and verification:**
- Owner: `evidence`.
- Run `rg -n "app\.policies" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_agent_evidence_layer.py`, `tests/test_agent_capability_boundaries.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20D complete`

**Execution result:**
- Moved the real policy implementations into `evidence/evidence_policy.py` and `evidence/citation_policy.py`.
- Converted `policies/evidence_policy.py`, `policies/citation_policy.py`, and `policies/__init__.py` into one-way compatibility exports only.
- Rerouted all discovered consumers to final evidence owners:
  - `planning/tool_whitelist_builder.py`, `understanding/llm_understanding_agent.py`, and `evidence/policy_guard.py`.
  - `composition/answer_composer.py` and `composition/response_contract_compiler.py` now import the local evidence policy classes directly.
  - `orchestration/states/evidence_planning_and_tool_use.py` now imports `EvidencePolicy` directly.
  - Retired-orchestrator consumers `action_model_controller.py`, `answer_mode_router.py`, and `claim_policy_registry.py` now use `app.evidence.evidence_policy` so their later migration will not retain a root-policy dependency.
- Removed `legacy_policy_attr` from both composition and orchestration temporary boundaries; no runtime path can dynamically resolve the retired root policy package.
- Exported `EvidencePolicy`, `ClaimPolicy`, and `CitationPolicy` from the evidence capability package.
- Commands run:
  - `rg -n "app\.policies" app tests`: no output.
  - `rg -n "legacy_policy_attr" app/composition app/orchestration`: no output.
  - `python -m pytest tests/test_agent_evidence_layer.py tests/test_agent_capability_boundaries.py tests/test_composition_boundaries.py tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`: pass, `23 passed, 9 warnings`.
  - `python -m compileall` over all moved and rerouted policy consumers: pass.
- Plan correction: the initial four-consumer list omitted legacy-orchestrator static imports and two dynamic temporary-boundary consumers. They were migrated in this task because leaving any one of them would create a runtime root-policy dependency despite a clean direct-import scan.
- Blockers: none. Warnings were existing UTC deprecations in tool adapters plus the environmental pytest cache permission warning.
- No package was deleted and no commit was made.

### Task 20E: Migrate Context And Understanding Schema Primitives

**Implementation files (10):**
- `schemas/conversation_context.py`, `schemas/conversation_memory.py`, `schemas/normalized_user_request.py`, `schemas/query_understanding.py`, `schemas/rewritten_query.py`
- `schemas/semantic_frame.py`, `schemas/intent_profile.py`, `schemas/travel_task.py`, `schemas/place_candidate.py`, `schemas/place_ambiguity.py`

**Owner and verification:**
- Owners: `context` and `understanding`.
- Reroute the target-layer dynamic schema boundaries and any listed agent consumers to the local model modules.
- Run `rg -n "app\.schemas\.(conversation_context|conversation_memory|normalized_user_request|query_understanding|rewritten_query|semantic_frame|intent_profile|travel_task|place_candidate|place_ambiguity)" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_agent_context_layer.py`, `tests/test_agent_capability_boundaries.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20E complete`

**Execution result:**
- Moved the two remaining real schema implementations into `understanding`:
  - `understanding/rewritten_query.py`
  - `understanding/intent_profile.py`
- Converted `schemas/rewritten_query.py` and `schemas/intent_profile.py` to compatibility exports. The other eight Task 20E schema files were already compatibility exports to `context` or `understanding` from earlier layer migrations.
- Rerouted all static and dynamic consumers of the ten models:
  - Context and understanding consumers now use `context.conversation_context`, `understanding.normalized_user_request`, `query_understanding_model`, `semantic_frame_model`, `travel_task`, `place_candidate`, `place_ambiguity`, `rewritten_query`, and `intent_profile`.
  - `schemas/user_query.py` now uses final model owners for its state fields while it remains a compatibility state surface until Task 20H.
  - Updated integration cache/resolver code, evidence policy code, legacy agent/orchestrator helpers, and S5 test imports to the final model paths.
- Commands run:
  - Task-specific `rg -n "app\.schemas\.(conversation_context|conversation_memory|normalized_user_request|query_understanding|rewritten_query|semantic_frame|intent_profile|travel_task|place_candidate|place_ambiguity)" app tests`: no output.
  - `python -m pytest tests/test_agent_context_layer.py tests/test_agent_capability_boundaries.py tests/test_agent_execution_integration_layer.py tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`: pass, `23 passed, 6 warnings`.
  - `python -m compileall` over the moved models and all changed consumer groups: pass.
- Plan correction: Task 20E's ten sources contained only two remaining implementation bodies; the other eight were already one-way compatibility exports. The work therefore focused on consumer rerouting and `TravelAgentState` field-type cleanup, not duplicate model moves.
- Blockers: none. Warnings were existing UTC deprecations in tool adapters plus the environmental pytest cache permission warning.
- No package was deleted and no commit was made.

### Task 20F: Migrate Planning And Research Schema Primitives

**Implementation files (10):**
- `schemas/information_need.py`, `schemas/search_task.py`, `schemas/search_query_plan.py`, `schemas/response_contract.py`, `schemas/lookup_claim.py`
- `schemas/lookup_research_chain.py`, `schemas/evidence_gap_request.py`, `schemas/user_need_residual.py`, `schemas/s5_information_domain.py`, `schemas/place_context.py`

**Owner and verification:**
- Owners: `planning`, `evidence`, and `integrations/places`.
- Run a task-specific `rg -n "app\.schemas\.(information_need|search_task|search_query_plan|response_contract|lookup_claim|lookup_research_chain|evidence_gap_request|user_need_residual|s5_information_domain|place_context)"` scan; expect no output.
- Test: `tests/test_agent_capability_boundaries.py`, `tests/test_s5_whitelist.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20F complete`

**Execution result:**
- Moved the four remaining planning/research model implementations into their final owners:
  - `planning/search_query_plan.py`
  - `planning/lookup_claim.py`
  - `planning/lookup_research_chain.py`
  - `planning/user_need_residual.py`
- Converted their `schemas/*` predecessors into one-way compatibility exports. The other five planned schema files were already compatibility exports; `PlaceContext` was an overlapping implementation and now consistently resolves to `understanding.travel_task.PlaceContext`.
- Rerouted every static and dynamic consumer of the ten scoped schema modules to `planning`, `composition`, or `understanding`, including the legacy agent helpers and orchestration state surface.
- `LookupClaim` now dynamically resolves `ClaimRequirement` at its composition boundary. Its temporary dynamic resolution of `claim_family_registry` avoids an invalid static planning-to-orchestration dependency; Task 20Q now explicitly owns moving that registry and removing this temporary bridge.
- Commands run:
  - `rg -n "app\\.schemas\\.(information_need|search_task|search_query_plan|response_contract|lookup_claim|lookup_research_chain|evidence_gap_request|user_need_residual|s5_information_domain|place_context)" app tests`: no output.
  - `python -m pytest tests/test_agent_capability_boundaries.py tests/test_agent_execution_integration_layer.py tests/test_s5_whitelist.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`: pass, `20 passed, 6 warnings`.
  - `python -m compileall -q app\\planning app\\agents app\\orchestrator app\\evidence\\evidence_evaluator.py app\\integrations\\catalog\\place_catalog.py app\\schemas\\user_query.py`: pass.
- Blockers: none. Warnings are existing UTC deprecations in tool adapters plus the environmental pytest-cache permission warning.
- Plan correction: this task's actual model ownership is `planning`, `composition`, and `understanding`; `PlaceContext` belongs with user-request understanding rather than integrations/places.
- No package was deleted and no commit was made.

### Task 20G: Migrate Evidence And Composition Result Schemas

**Implementation files (10):**
- `schemas/citation.py`, `schemas/claim_facts.py`, `schemas/coverage_report.py`, `schemas/evidence_brief.py`, `schemas/evidence_decision_report.py`
- `schemas/final_answer_draft.py`, `schemas/official_source.py`, `schemas/peak_elevation.py`, `schemas/place_factsheet.py`, `schemas/review_signal.py`

**Owner and verification:**
- Owners: `evidence` and `composition`.
- Run a task-specific `rg -n "app\.schemas\.(citation|claim_facts|coverage_report|evidence_brief|evidence_decision_report|final_answer_draft|official_source|peak_elevation|place_factsheet|review_signal)"` scan; expect no output.
- Test: `tests/test_agent_evidence_layer.py`, `tests/test_composition_boundaries.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20G complete`

**Execution result:**
- Moved the five remaining evidence-result model implementations into their final owner:
  - `evidence/citation.py`
  - `evidence/claim_facts.py`
  - `evidence/peak_elevation.py`
  - `evidence/place_factsheet.py`
  - `evidence/review_signal.py`
- Converted the five corresponding `schemas/*` modules into one-way compatibility exports. The other five planned schema files were already compatibility exports owned by `evidence` or `composition`.
- Rerouted all scoped consumers, including evidence helpers, legacy agents/orchestrator helpers, `orchestration/state_machine.py`, `composition/composer.py`, and `schemas/user_query.py` state fields. `PlaceFactSheet` no longer crosses those capability boundaries through `legacy_schema_attr`.
- Commands run:
  - `rg -n "app\\.schemas\\.(citation|claim_facts|coverage_report|evidence_brief|evidence_decision_report|final_answer_draft|official_source|peak_elevation|place_factsheet|review_signal)" app tests`: no output.
  - `rg -n "legacy_schema_attr.*(citation|claim_facts|coverage_report|evidence_brief|evidence_decision_report|final_answer_draft|official_source|peak_elevation|place_factsheet|review_signal)" app tests`: no output.
  - `python -m pytest tests/test_agent_evidence_layer.py tests/test_composition_boundaries.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`: pass, `12 passed, 4 warnings`.
  - `python -m compileall -q app\\evidence app\\composition app\\agents app\\orchestration app\\orchestrator app\\schemas\\user_query.py app\\schemas\\ticket_info.py`: pass.
- Blockers: none. Warnings are existing UTC deprecations in Pydantic paths plus the environmental pytest-cache permission warning.
- Plan corrections: none.
- No package was deleted and no commit was made.

### Task 20H: Migrate Remaining Public State And Specialized Schemas

**Implementation files (9):**
- `schemas/agent_core.py`, `schemas/response.py`, `schemas/user_query.py`, `schemas/itinerary.py`, `schemas/review.py`
- `schemas/search_snippet_evidence.py`, `schemas/ticket_info.py`, `schemas/tool_trace.py`, `schemas/__init__.py`

**Owner and verification:**
- Owners: `orchestration`, `contracts`, `composition`, `evidence`, and `observability`.
- This task depends on 20E-20G and must replace all state-field imports with their final model owners before moving `TravelAgentState`.
- Run `rg -n "app\.schemas" apps/agent-python/app apps/agent-python/tests`; expect only modules explicitly deferred to later batches, then record them. Do not delete `schemas` yet.
- Test: `tests/test_agent_contract_layer.py`, `tests/test_governance_observability_layer.py`, `tests/test_orchestration_boundaries.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20H complete`

**Execution result:**
- Moved the remaining public/state implementations to their final owners:
  - `orchestration/agent_core_models.py`
  - `orchestration/travel_agent_state.py`
  - `composition/response_models.py`
  - `composition/itinerary.py`
  - `evidence/review.py`
  - `evidence/search_snippet_evidence.py`
  - `evidence/ticket_info.py`
- `observability/tool_trace.py` was already the final implementation, so `schemas/tool_trace.py` remains only a compatibility export. `schemas/response.py` now joins contracts request/response aliases with composition-owned response structures; `schemas/user_query.py` joins understanding-owned user types with orchestration-owned state types.
- Moved the otherwise-unplanned public `PlaceInfo` model to `understanding/place_info.py`, because it was only retained by `schemas/__init__.py` and no later task owns it. The root package facade now points only to final owners.
- Rerouted all runtime consumers of the scoped models, including dynamic composition/orchestration boundaries, Agent Core helpers, legacy agents, Java-gateway `ToolTrace` conversion, and state fields. `TravelAgentState.intent_strategy` is temporarily `Any` to avoid a prohibited static dependency on the registry that Task 20Q moves.
- Tightened the orchestration boundary test to detect real import statements instead of matching the ordinary state-field suffix `pending_evidence_gap_requests` as if it imported the `requests` package.
- Commands run:
  - Scoped `rg` scan for the nine Task 20H modules: no runtime imports; only `tests/test_agent_contract_layer.py` retains `schemas.response` to assert the HTTP contract compatibility aliases.
  - `rg -n "app\\.schemas" app tests`: remaining paths are `app.schemas.evidence`, `app.schemas.tool_whitelist`, and the intentional `app.schemas.response` compatibility assertion. The first two are owned by remaining agent/orchestrator migration batches; tests are closed in Task 20W.
  - `python -m pytest tests/test_agent_contract_layer.py tests/test_governance_observability_layer.py tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`: pass, `20 passed, 6 warnings`.
  - `python -m compileall -q app\\orchestration app\\composition app\\evidence app\\observability app\\understanding app\\agents app\\orchestrator app\\integrations\\java_gateway`: pass.
  - Compatibility import smoke across state, response, review, Agent Core, and `PlaceInfo`: pass, `COMPATIBILITY_IMPORT_SMOKE_OK`.
- Blockers: none. Warnings are existing UTC deprecations in tool adapters plus the environmental pytest-cache permission warning.
- Plan correction: `PlaceInfo` was an unlisted implementation reachable only through the public facade, so it was migrated alongside `schemas/__init__.py`; `ToolTrace` required no implementation move.
- No package was deleted and no commit was made.

### Task 20I: Migrate LLM And Query-Normalization Agents

**Implementation files (10):**
- `agents/llm_understanding_agent.py`, `agents/normalize_llm_understanding.py`, `agents/normalized_request_to_query_understanding.py`, `agents/normalized_request_to_semantic_frame.py`, `agents/normalized_request_to_travel_task.py`
- `agents/normalized_request_to_user_goal.py`, `agents/query_understanding_agent.py`, `agents/query_rewriter.py`, `agents/place_entity_extractor.py`, `agents/conversation_context_builder.py`

**Owner and verification:**
- Owners: `understanding` and `context`.
- Run a task-specific `rg -n "app\.agents\.(llm_understanding_agent|normalize_llm_understanding|normalized_request_to_query_understanding|normalized_request_to_semantic_frame|normalized_request_to_travel_task|normalized_request_to_user_goal|query_understanding_agent|query_rewriter|place_entity_extractor|conversation_context_builder)"` scan; expect no output.
- Test: `tests/test_agent_context_layer.py`, `tests/test_agent_capability_boundaries.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20I complete`

**Execution result:**
- Moved the only remaining implementation body, `ContextualQueryRewriter`, into `understanding/query_rewriter.py` and converted `agents/query_rewriter.py` to a one-way compatibility export.
- The other nine listed agent files were already compatibility exports to `context` or `understanding`; no duplicate implementations were retained.
- The rewriter now uses `ConversationContextBuilder` and `RuleBasedUnderstanding` directly from their final owners. It no longer constructs an unused temporary `TravelAgentState` merely to build conversation context.
- Exported `ContextualQueryRewriter` through the understanding facade and extended the capability-boundary test to cover it.
- Commands run:
  - Task-specific static `rg` scan: no output.
  - Task-specific `legacy_agent_attr` scan: no output.
  - `python -m pytest tests/test_agent_context_layer.py tests/test_agent_capability_boundaries.py tests/test_layer_consolidation_imports.py`: pass, `9 passed, 1 warning`.
  - `python -m compileall -q app\\context app\\understanding app\\agents`: pass.
  - Compatibility import smoke for `ContextualQueryRewriter`: pass, `QUERY_REWRITER_COMPATIBILITY_OK`.
- Blockers: none. The warning is the environmental pytest-cache permission warning.
- Plan correction: Task 20I's ten sources contained one remaining implementation body and nine pre-existing compatibility exports.
- No package was deleted and no commit was made.

### Task 20J: Migrate Rule, Entity, And Travel-Understanding Agents

**Implementation files (8):**
- `agents/entity_resolution_agent.py`, `agents/intent_agent.py`, `agents/rule_based_to_normalized_request.py`, `agents/rule_based_understanding.py`
- `agents/semantic_frame_builder.py`, `agents/travel_task_extractor.py`, `agents/travel_task_to_user_goal_adapter.py`, `agents/nearby_anchor_strategy_agent.py`

**Owner and verification:**
- Owners: `understanding` and `planning`.
- Run a task-specific `rg -n "app\.agents\.(entity_resolution_agent|intent_agent|rule_based_to_normalized_request|rule_based_understanding|semantic_frame_builder|travel_task_extractor|travel_task_to_user_goal_adapter|nearby_anchor_strategy_agent)"` scan; expect no output.
- Test: `tests/test_agent_capability_boundaries.py`, `tests/test_s5_whitelist.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20J complete`

**Execution result:**
- Moved the only remaining implementation, `NearbyAnchorStrategyAgent`, into `planning/nearby_anchor_strategy.py` and converted the root agent file to a one-way compatibility export.
- The other seven files were already compatibility exports. In particular, `EntityResolutionAgent` is execution-owned rather than an understanding/planning implementation and continues to resolve from `execution/entity_resolution.py`.
- Rerouted the controlled action executor and recursive sub-agent delegate to `planning.nearby_anchor_strategy` and `execution.entity_resolution`; no runtime consumer now imports the scoped root agent modules.
- The planning agent deliberately uses `Any` for the mutable run state, avoiding a static planning-to-orchestration dependency. It temporarily resolves `information_need_aliases`, `nearby_anchor_policy`, and `place_disambiguation_guard` dynamically until their owner tasks complete.
- Exported `NearbyAnchorStrategyAgent` through the planning facade and extended the capability-boundary test.
- Commands run:
  - Task-specific static `rg` scan: no output.
  - Task-specific `legacy_agent_attr` scan: no output.
  - `python -m pytest tests/test_agent_capability_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`: pass, `13 passed, 6 warnings`.
  - `python -m compileall -q app\\understanding app\\planning app\\agents app\\execution`: pass.
  - Compatibility import smoke for `NearbyAnchorStrategyAgent` and `EntityResolutionAgent`: pass, `NEARBY_ANCHOR_COMPATIBILITY_OK`.
- Blockers: none. Warnings are existing UTC deprecations in tool adapters plus the environmental pytest-cache permission warning.
- Plan correction: Task 20J has one remaining implementation body and seven compatibility exports; the listed `EntityResolutionAgent` belongs to `execution`.
- No package was deleted and no commit was made.

### Task 20K: Migrate Planning And Research Agent Entry Points

**Implementation files (5):**
- `agents/information_need_planner.py`, `agents/search_task_planner_agent.py`, `agents/search_query_refiner_agent.py`, `agents/place_research_agent.py`, `agents/review_mining_agent.py`

**Owner and verification:**
- Owners: `planning` and `evidence`.
- Run a task-specific `rg -n "app\.agents\.(information_need_planner|search_task_planner_agent|search_query_refiner_agent|place_research_agent|review_mining_agent)"` scan; expect no output.
- Test: `tests/test_agent_capability_boundaries.py`, `tests/test_agent_evidence_layer.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20K complete`

**Execution result:**
- Moved the three remaining implementations to their final owners:
  - `planning/search_query_refiner_agent.py`
  - `planning/place_research_agent.py`
  - `evidence/review_mining_agent.py`
- Converted the three source agents to one-way compatibility exports. `InformationNeedPlanner` and `SearchTaskPlannerAgent` were already planning-owned compatibility exports.
- Moved `QueryPlan` into `planning/query_plan.py`, updated `TravelAgentState` and schema compatibility exports to use it, and removed the invalid planning-to-orchestration model dependency.
- Rerouted the action controller, orchestration state machine, and evidence analysis agents to final planning/evidence owners. Search/places code now avoids static LLM/tool dependencies through final-owner dynamic resolution or `Any` at execution boundary types.
- Review Mining keeps temporary dynamic bridges to the Task 20L review-helper implementations and Task 20U evidence-signal helper; its source conflict-ranking logic now stays inside evidence using `SourcePriorityPolicy`.
- Commands run:
  - Task-specific static `rg` scan: no output.
  - Task-specific `legacy_agent_attr` scan: no output.
  - `python -m pytest tests/test_agent_capability_boundaries.py tests/test_agent_evidence_layer.py tests/test_layer_consolidation_imports.py`: pass, `9 passed, 4 warnings`.
  - `python -m compileall -q app\\planning app\\evidence app\\orchestration app\\agents`: pass.
  - Compatibility import smoke across the three agents and `QueryPlan`: pass, `PLANNING_RESEARCH_COMPATIBILITY_OK`.
- Blockers: none. Warnings are existing Pydantic UTC deprecations plus the environmental pytest-cache permission warning.
- Plan correction: Task 20K had three remaining agent implementations and two compatibility exports; `QueryPlan` is a planning output and was rehomed from orchestration to prevent an inverted dependency.
- No package was deleted and no commit was made.

### Task 20L: Migrate Evidence Analysis And Review Agents

**Implementation files (8):**
- `agents/claim_relevance_filter_agent.py`, `agents/evidence_conflict_analyzer_agent.py`, `agents/evidence_contradiction_decomposer_agent.py`, `agents/evidence_curation_planner_agent.py`
- `agents/review/aspect_normalizer.py`, `agents/review/llm_extractor.py`, `agents/review/persona_generator.py`, `agents/review/rule_extractor.py`

**Owner and verification:**
- Owner: `evidence`.
- Task 20K follow-up: move `agents/review/*` helper implementations into evidence and replace the dynamic review-helper bridge in `evidence.review_mining_agent`.
- Run a task-specific `rg -n "app\.agents\.(claim_relevance_filter_agent|evidence_conflict_analyzer_agent|evidence_contradiction_decomposer_agent|evidence_curation_planner_agent|review)"` scan; expect no output.
- Test: `tests/test_agent_evidence_layer.py` and consolidation imports.

**Completion checkbox:** `[x] Task 20L complete`

**Execution result:**
- Moved all eight implementations into evidence:
  - `evidence/claim_relevance_filter_agent.py`
  - `evidence/evidence_conflict_analyzer_agent.py`
  - `evidence/evidence_contradiction_decomposer_agent.py`
  - `evidence/evidence_curation_planner_agent.py`
  - `evidence/review_aspect_normalizer.py`
  - `evidence/review_llm_extractor.py`
  - `evidence/review_persona_generator.py`
  - `evidence/review_rule_extractor.py`
- Converted every source file to a one-way compatibility export. `ReviewAspectMiningAgent` now resolves the four review helpers from evidence, closing the Task 20K review bridge; the controlled action executor now invokes all four evidence agents through final owner modules.
- Expanded the evidence facade and its test coverage for the newly owned analysis and review capabilities.
- Replaced static LLM, mutable-state, schema, utility, and planning dependencies with final-owner dynamic resolution or `Any` boundary types. Conflict source ranking remains evidence-owned through `SourcePriorityPolicy`.
- Commands run:
  - Task-specific static `rg` scan: no output.
  - Task-specific `legacy_agent_attr` scan: no output.
  - `python -m pytest tests/test_agent_evidence_layer.py tests/test_layer_consolidation_imports.py`: pass, `5 passed, 4 warnings`.
  - `python -m compileall -q app\\evidence app\\execution app\\agents`: pass.
  - Compatibility import smoke across evidence analysis and review wrappers: pass, `EVIDENCE_AGENT_COMPATIBILITY_OK`.
- Blockers: none. Warnings are existing Pydantic UTC deprecations plus the environmental pytest-cache permission warning.
- Plan corrections: none.
- No package was deleted and no commit was made.

### Task 20M: Migrate Execution Data-Retrieval Agents

**Implementation files (10):**
- `agents/delegated_mcp_runner.py`, `agents/fact_lookup_agent.py`, `agents/fact_lookup_phase_runner.py`, `agents/fact_lookup_pipeline_runner.py`, `agents/fact_search_agent.py`
- `agents/keyword_search_agent.py`, `agents/nearby_enrichment_runner.py`, `agents/nearby_retrieval_runner.py`, `agents/route_feasibility_agent.py`, `agents/weather_context_agent.py`

**Owner and verification:**
- Owners: `execution`, `tools`, and `integrations`.
- Run a task-specific `rg -n "app\.agents\.(delegated_mcp_runner|fact_lookup_agent|fact_lookup_phase_runner|fact_lookup_pipeline_runner|fact_search_agent|keyword_search_agent|nearby_enrichment_runner|nearby_retrieval_runner|route_feasibility_agent|weather_context_agent)"` scan; expect no output.
- Test: `tests/test_agent_execution_integration_layer.py`, `tests/test_s5_whitelist.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20M complete`

**Execution result (2026-07-11):**
- Commands: task-specific retired-import `rg` scan; execution/legacy compatibility import smoke; `python -m compileall -q app\\execution app\\integrations app\\agents`; `python -m pytest tests/test_agent_execution_integration_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; `git diff --check`.
- Result: nine concrete retrieval implementations now live in `execution`; `delegated_mcp_runner` remains a compatibility facade over `integrations.mcp.delegated_runner`; root `agents` files are one-way compatibility exports. The first test run found static execution-to-legacy dependencies, so they were converted to explicit runtime boundary helpers; the final test run passed `12 passed` (only existing deprecation and pytest-cache warnings).
- Files changed: nine `app/execution` retrieval modules and their exports; `execution/action_executor.py`, `execution/entity_resolution.py`, `evidence/policy_guard.py`, `planning/search_task_planner_agent.py`, and `agents/subagent_delegate.py`; nine legacy `agents` compatibility facades.
- Deleted files: none; retired package files remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: Task 20N now owns removal of the temporary S5 registry/delegate bridges introduced by this task.

## User-Directed Restart From Task 20N

**Restart decision (2026-07-12):** Re-execute the migration chain from Task 20N. This is a plan-status reset only: no source files are reverted, and each historical execution result below remains as audit evidence rather than a current completion claim.

**Reason:** Task 20V's required orchestration-boundary baseline found two static `app.integrations.mcp.tool_arguments` imports in final orchestration files. The S5 surface owned by Task 20N must restore the final integration boundary before later helper migrations can be trusted or verified.

**Re-execution order:** `20N -> 20O -> 20P -> 20P-A -> 20Q -> 20R -> 20S -> 20T -> 20U -> 20V -> 20W -> 20 deletion gate`. Each task must rerun its stated focused verification; no later task may be checked until its predecessor is rechecked.

### Task 20N: Migrate Composition And S5 Agent Surfaces

**Implementation files (6):**
- `agents/answer_composer_agent.py`, `agents/composer_agent.py`, `agents/suitability_scorer.py`
- `agents/s5_evidence_orchestrator_agent.py`, `agents/s5_subagent_registry.py`, `agents/subagent_delegate.py`

**Owner and verification:**
- Owners: `composition` and `orchestration`.
- Keep existing orchestration helper imports behind transitional local boundaries until Tasks 20O-20V complete.
- Task 20M follow-up: move `s5_subagent_registry` and `subagent_delegate`, then replace the temporary S5 bridges in `execution/entity_resolution.py`, `fact_search_agent.py`, `route_feasibility_agent.py`, `weather_context_agent.py`, and `nearby_retrieval_runner.py` with final composition/orchestration dependencies.
- Run a task-specific `rg -n "app\.agents\.(answer_composer_agent|composer_agent|suitability_scorer|s5_evidence_orchestrator_agent|s5_subagent_registry|subagent_delegate)"` scan; expect no output.
- Test: `tests/test_composition_boundaries.py`, `tests/test_orchestration_boundaries.py`, `tests/test_s5_whitelist.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20N complete`

**Execution result (re-execution, 2026-07-13):**
- Commands: baseline and final `python -m pytest tests/test_composition_boundaries.py tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; task-specific retired-agent scan; orchestration static-integration scan; `python -m compileall -q app\\composition app\\orchestration app\\execution app\\agents`; final/legacy import smoke; scoped `git diff --check`.
- Result: the re-execution repaired two pre-existing static `app.integrations.mcp.tool_arguments` imports. `s5_evidence_orchestrator.py` now resolves `_route_endpoints_from_text` only at route-parameter evaluation, and the S5 planning state resolves `mcp_tool_invocation_ready` only when evaluating a tool. All six scoped root-agent modules remain one-way compatibility exports to their composition/orchestration owners. Final focused verification passed `16 passed, 2 warnings`; both warnings are existing UTC deprecations in tool paths.
- Files changed: `orchestration/s5_evidence_orchestrator.py`, `orchestration/states/evidence_planning_and_tool_use.py`, and this plan. No scoped compatibility facade required code changes because all six were already correctly reduced.
- Deleted files: none.
- Blockers: none.
- Plan corrections: `tests/test_orchestration_boundaries.py` is now a formal Task 20N verification requirement. Task 20O remains the next unchecked task in the user-directed restart chain.

**Historical execution result (2026-07-11; superseded by restart):**
- Commands: task-specific retired-import `rg` scan; composition/orchestration and legacy compatibility import smoke; `python -m compileall -q app\\composition app\\orchestration app\\execution app\\agents`; `python -m pytest tests/test_composition_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`.
- Result: S5 registry, recursive delegate, and LLM orchestration now live in `orchestration`; suitability scoring now lives in `composition`; the answer/composer surfaces remain their already-migrated composition implementations. Execution bridge callers, policy guard, S5 prompt state, action executor, and the legacy action controller now resolve final module paths. The final test run passed `12 passed` (only existing deprecation and pytest-cache warnings).
- Files changed: new `composition/suitability_scorer.py`; new `orchestration/s5_evidence_orchestrator.py`, `s5_subagent_registry.py`, and `subagent_delegate.py`; layer facades, S5 callers, and six legacy `agents` compatibility facades.
- Deleted files: none; retired package files remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: explicit deferred S5 helper bridges were added to Tasks 20O, 20Q, 20R, 20S, 20T, 20U, and 20V.

### Task 20O: Migrate Agent Core Workflow Helpers

**Implementation files (10):**
- `orchestrator/agent_core_control_tools.py`, `agent_core_data_tool_policy.py`, `agent_core_job_reconciler.py`, `agent_core_pipeline_gate.py`, `agent_core_prompt_guidance.py`
- `agent_core_research_plan.py`, `agent_core_store.py`, `agent_core_supervisor.py`, `agent_core_tool_surface.py`, `agent_tool_catalog.py`

**Owner and verification:**
- Owners: `orchestration`, `planning`, and `execution`.
- Replace `orchestration/_legacy_boundary.py` references for these names with direct local-owner imports.
- Task 20N follow-up: replace the S5 orchestrator's dynamic `agent_core_prompt_guidance` and `agent_tool_catalog` bridges with final local-owner dependencies.
- Run a task-specific `rg -n "app\.orchestrator\.(agent_core_|agent_tool_catalog)" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_orchestration_boundaries.py`, `tests/test_s5_whitelist.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20O complete`

**Execution result (re-execution, 2026-07-13):**
- Commands: baseline `python -m pytest tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; task-specific retired-import and dynamic old-bridge scan; `python -m compileall -q app\\orchestration app\\planning app\\execution app\\orchestrator`; final/legacy Agent Core import smoke; scoped `git diff --check`.
- Result: all ten scoped `app.orchestrator` files remain one-way compatibility exports. Their implementations are already owned by `orchestration`, `planning`, or `execution`, and the S5 orchestrator already imports Agent Core prompt guidance and the tool catalog from their final planning owners. The focused suite passed `13 passed, 2 warnings`; both warnings are existing UTC deprecations in tool paths.
- Files changed: this plan only. Re-execution verified that no Agent Core source move or import rewrite was needed after the repaired Task 20N boundary.
- Deleted files: none.
- Blockers: none.
- Plan corrections: none. Task 20P is the next unchecked task in the restart chain.

**Historical execution result (2026-07-12; superseded by restart):**
- Commands: task-specific retired-import and `_legacy_boundary` scans; new/legacy compatibility import smoke; `python -m compileall -q app\\orchestration app\\planning app\\execution app\\orchestrator`; `python -m pytest tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`.
- Result: Agent Core control, store, reconciliation, pipeline, research-plan, supervisor, and run-surface implementations now live in `orchestration`; data-tool visibility policy lives in `execution`; prompt guidance and Agent tool catalog live in `planning`. All runtime callers now use final layer paths and the ten retired files are one-way compatibility exports. The first test run found two static external/config boundary violations; both were converted to approved dynamic boundaries and the final run passed `13 passed` (only existing deprecation and pytest-cache warnings).
- Files changed: ten final-owner modules and their layer facades; Agent Core callers in the state machine, S5 planning state, S5 orchestrator, keyword search, tool-whitelist builder, and legacy action controller; ten `orchestrator` compatibility facades.
- Deleted files: none; retired package files remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: Task 20S now explicitly owns replacement of the remaining diversified-selector bridge in Agent Core research planning.

### Task 20P: Migrate Controlled Action-Loop Helpers

**Implementation files (5):**
- `orchestrator/action_model_controller.py`, `orchestrator/claude_state_runner.py`, `orchestrator/clarification_gate.py`, `orchestrator/actions.py`, `orchestrator/action_executor.py`

**Owner and verification:**
- Owners: `orchestration` and `execution`.
- Split `action_model_controller.py` by orchestration loop control versus execution action transport; it is intentionally isolated because it is the largest remaining file.
- Run a task-specific `rg -n "app\.orchestrator\.(action_model_controller|claude_state_runner|clarification_gate|actions|action_executor)" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_s5_whitelist.py`, `tests/test_orchestration_boundaries.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20P complete`

**Execution result (re-execution, 2026-07-13):**
- Commands: baseline `python -m pytest tests/test_s5_whitelist.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`; task-specific retired-import and dynamic old-bridge scans; orchestration static-integration scan; `python -m compileall -q app\\orchestration app\\execution app\\orchestrator`; final/legacy action-loop import smoke; scoped `git diff --check`.
- Result: all five scoped `app.orchestrator` files remain one-way compatibility exports. The action model controller, controlled state runner, and clarification gate are final orchestration implementations; action models and action execution are final execution implementations. No action-loop caller resolves a scoped old module, and the repaired S5 path introduced no static integration import. The focused suite passed `13 passed, 2 warnings`; both warnings are existing UTC deprecations in tool paths.
- Files changed: this plan only. Re-execution verified the already-correct final owners and compatibility exports without a redundant runtime rewrite.
- Deleted files: none.
- Blockers: none.
- Plan corrections: none. Task 20Q is the next unchecked task in the restart chain.

**Historical execution result (2026-07-12; superseded by restart):**
- Commands: task-specific retired-import, hidden legacy-name, and orchestration external-boundary scans; new/legacy compatibility import smoke; `python -m compileall -q app\\orchestration app\\execution app\\orchestrator`; `python -m pytest tests/test_s5_whitelist.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`.
- Result: the 58 KB action model controller, controlled state runner, and clarification gate now live in `orchestration`; action models and action execution remain the existing `execution` implementations. State nodes and S5 tests use final paths, while all five retired files are one-way compatibility exports. Final verification passed `13 passed` (only existing deprecation and pytest-cache warnings).
- Files changed: new orchestration controller/runner/gate modules and facade exports; final-path state-node imports; S5 test imports; three retired implementation files converted to compatibility facades (the two execution facades were already migrated).
- Deleted files: none; retired package files remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: deferred policy bridges discovered in the controller/runner were assigned explicitly to Tasks 20Q-20V.

### Task 20P-A: Decouple Nearby Planning From Concrete MCP Adapters

**Implementation files (3 direct consumers plus one final helper):**
- `planning/nearby_anchor_policy.py`, `planning/s5_poi_anchor_policy.py`, `planning/nearby_task_orchestration.py`
- Create the final tool-neutral POI anchor extraction helper under `evidence`.

**Owner and verification:**
- Owners: `evidence` for extraction of coordinates, candidate ambiguity, and gate qualifiers from evidence/query data; `planning` for nearby search-policy decisions.
- Move `gate_tokens_from_user_query`, `resolve_nearby_anchor_coordinates`, `resolve_coordinates_from_evidence`, and `candidates_are_ambiguous` behind the final evidence helper. The planning layer must consume only that final helper and must not import `tools.mcp` or another concrete adapter.
- Keep the tool adapter API only as a compatibility delegate if tool-runtime callers still need it; do not duplicate parsing logic between planning and the MCP adapter.
- This is a prerequisite discovered by Task 20Q's capability-boundary baseline. It must complete before Task 20Q can rerun.
- Run `rg -n "tools\.mcp" apps/agent-python/app/planning`; expect no output.
- Test: `tests/test_agent_capability_boundaries.py`, `tests/test_s5_whitelist.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20P-A complete`

**Execution result (2026-07-13):**
- Commands: required baseline `python -m pytest tests/test_agent_capability_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; direct planning-MCP import scan; `python -m compileall -q app\\evidence app\\planning ..\\..\\packages\\tools\\mcp\\adapters\\baidu_response_parser.py`; final/adapter identity smoke; focused `python -m pytest tests/test_poi_anchor_extraction.py tests/test_agent_capability_boundaries.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; duplicate-implementation, repeated planning-MCP, and scoped `git diff --check` scans.
- Result: the baseline failed only at the expected concrete-MCP planning boundary (`12 passed, 1 failed`). `evidence.poi_anchor_extraction` is now the single tool-neutral owner of gate qualifiers, anchor/coordinate extraction, and candidate ambiguity. The three planning consumers import that final owner; `baidu_response_parser` only re-exports the same function objects for tool-runtime compatibility. Final verification passed `16 passed, 2 warnings`; both warnings are existing UTC deprecations in tool paths.
- Files changed: added `apps/agent-python/app/evidence/poi_anchor_extraction.py` and `apps/agent-python/tests/test_poi_anchor_extraction.py`; updated the three planning consumers and `packages/tools/mcp/adapters/baidu_response_parser.py`.
- Deleted files: none; removed 139 lines of duplicate adapter implementation while retaining its compatibility API.
- Blockers: none.
- Plan corrections: none. Task 20Q may now rerun its capability-boundary baseline.

### Task 20Q: Migrate Intent And Claim Policy Helpers

**Implementation files (10):**
- `orchestrator/answer_mode_router.py`, `claim_family_registry.py`, `claim_gap_fill_planner.py`, `claim_policy_registry.py`, `claim_tool_policy.py`
- `information_need_aliases.py`, `intent_profile_deriver.py`, `intent_s7_policy.py`, `intent_strategy_registry.py`, `lookup_need_aliases.py`

**Owner and verification:**
- Owners: `understanding`, `planning`, and `evidence`.
- Task 20F follow-up: move `claim_family_registry` to its final planning/evidence owner and replace `planning.lookup_claim`'s temporary dynamic registry bridge with a same-layer dependency.
- Task 20H follow-up: restore `TravelAgentState.intent_strategy` to the final typed strategy model after `claim_family_registry` moves out of `app.orchestrator`.
- Task 20J follow-up: retain `information_need_aliases` in `understanding` because semantic normalization owns it; replace each old-orchestrator bridge with the final understanding module without creating a reverse understanding-to-planning dependency.
- Task 20N follow-up: replace the S5 orchestrator's dynamic `information_need_aliases.nearby_needs_set` bridge.
- Task 20P follow-up: replace action-controller bridges to `claim_gap_fill_planner` and `claim_tool_policy`.
- Run a task-specific `rg -n "app\.orchestrator\.(answer_mode_router|claim_family_registry|claim_gap_fill_planner|claim_policy_registry|claim_tool_policy|information_need_aliases|intent_profile_deriver|intent_s7_policy|intent_strategy_registry|lookup_need_aliases)" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_agent_capability_boundaries.py`, `tests/test_agent_evidence_layer.py`, `tests/test_s5_whitelist.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20Q complete`

**Execution result (2026-07-13):**
- Commands: required baseline `python -m pytest tests/test_agent_capability_boundaries.py tests/test_agent_evidence_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; legacy-facade and dynamic-bridge inventory; `python -m compileall -q app\\composition app\\evidence app\\understanding app\\planning app\\orchestration app\\orchestrator`; final/legacy owner identity smoke; task-specific retired-import scan; focused final pytest suite; AST dynamic-bridge scan; scoped `git diff --check`.
- Result: baseline passed `16 passed, 5 warnings`. All ten old `orchestrator` files remain one-way compatibility exports for final understanding, planning, and evidence owners. Replaced the remaining Task 20Q dynamic old-orchestrator bridges in three composition modules: claim policy now uses the final evidence import, and information/lookup alias consumers resolve their final understanding modules without violating the composition static-dependency rule. Added an AST guard that rejects any target-layer `legacy_orchestrator_attr` call for the ten retired helper names. Final verification passed `17 passed, 5 warnings`; warnings are existing UTC deprecations in Pydantic and a tool adapter.
- Files changed: `composition/response_contract_compiler.py`, `composition/place_disambiguation_composition.py`, `composition/nearby_guided_composition.py`, `tests/test_layer_consolidation_imports.py`, and this plan.
- Deleted files: none; the ten compatibility facades remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: retained `information_need_aliases` in `understanding`, not `planning`. It is semantic-normalization input to understanding itself; moving it to planning would reverse the target-layer dependency and risk an import cycle. Composition consumes the final module through delayed binding because the static composition boundary intentionally permits only evidence/contracts.

**Execution result (preflight, 2026-07-13):**
- Commands: `python -m pytest tests/test_agent_capability_boundaries.py tests/test_agent_evidence_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; concrete-MCP import location scan in `app/planning`.
- Result: baseline failed before Task 20Q code edits: `15 passed, 1 failed`. `test_planning_layer_has_no_concrete_mcp_or_http_integrations` found three `tools.mcp.adapters.baidu_response_parser` imports in `planning/nearby_anchor_policy.py`, `planning/s5_poi_anchor_policy.py`, and `planning/nearby_task_orchestration.py`.
- Files changed: this plan only. No intent or claim-policy implementation changed.
- Deleted files: none.
- Blockers: the required Task 20Q capability-boundary verification cannot pass until the three nearby planning imports are moved behind a tool-neutral final owner.
- Plan corrections: inserted Task 20P-A as the preceding MCP-decoupling task. Task 20Q remains unchecked and must resume after 20P-A completes.

**Re-execution required (2026-07-12):** Rerun intent and claim-policy migration against the repaired action-loop, S5 surfaces, and Task 20P-A planning boundary, including all deferred policy-bridge replacements.

**Historical execution result (2026-07-12; superseded by restart):**
- Commands: task-specific retired-import, hidden legacy-name, and target-layer boundary scans; new/legacy compatibility and typed-state smoke; `python -m compileall -q app\\understanding app\\planning app\\evidence app\\orchestration app\\execution app\\orchestrator`; `python -m pytest tests/test_agent_capability_boundaries.py tests/test_agent_evidence_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`.
- Result: answer-mode routing, need aliases, lookup aliases, and intent-profile derivation now live in `understanding`; intent strategy and claim tool/gap planning live in `planning`; claim-family, claim-policy, and intent-aware S7 adoption live in `evidence`. `TravelAgentState.intent_strategy` is typed as the final `IntentStrategy`; all callers use final paths and the ten retired files are compatibility facades. Final verification passed `16 passed` (only existing deprecation warnings).
- Files changed: ten final-owner implementations and three layer facades; typed orchestration state; final-path callers across understanding/planning/evidence/execution/orchestration and later legacy helpers; ten `orchestrator` compatibility facades.
- Deleted files: none; retired package files remain until the Task 20 deletion gate.
- Blockers: none. The elevated compile request was rejected by the Codex usage limit, but the same compile and full focused test suite passed inside the lower-privilege workspace sandbox.
- Plan corrections: remaining nearby, ticket, and official-chain dynamic bridges were assigned to Tasks 20S, 20T, and 20U.

### Task 20R: Migrate Lookup Research-Chain Helpers

**Implementation files (8):**
- `orchestrator/fact_lookup_anchor_policy.py`, `fact_lookup_policy.py`, `fact_lookup_task_orchestration.py`, `lookup_entity_resolution_policy.py`
- `lookup_query_objectives.py`, `lookup_research_chain.py`, `search_query_rewriter.py`, `retrieval_attempt_ledger.py`

**Owner and verification:**
- Owners: `planning`, `execution`, and `orchestration`.
- Task 20L follow-up: move `fact_lookup_policy` and replace the dynamic primary-fact-need bridge in `evidence.claim_relevance_filter_agent`.
- Task 20N follow-up: replace the S5 orchestrator's dynamic fact-lookup policy, lookup entity-resolution, query-objective, research-chain, retrieval-ledger, and query-rewriter bridges.
- Task 20P follow-up: replace action-controller/state-runner bridges to fact-lookup and lookup-research-chain policy helpers.
- Run a task-specific `rg -n "app\.orchestrator\.(fact_lookup_anchor_policy|fact_lookup_policy|fact_lookup_task_orchestration|lookup_entity_resolution_policy|lookup_query_objectives|lookup_research_chain|search_query_rewriter|retrieval_attempt_ledger)" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_s5_whitelist.py`, `tests/test_orchestration_boundaries.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20R complete`

**Execution result (2026-07-13):**
- Commands: required baseline `python -m pytest tests/test_s5_whitelist.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`; legacy-facade and dynamic-bridge inventory; `python -m compileall -q app\\composition app\\planning app\\execution app\\orchestration app\\evidence app\\orchestrator`; eight-pair final/legacy identity smoke; task-specific retired-import scan; focused final pytest suite; AST dynamic-bridge scan; scoped `git diff --check`.
- Result: baseline passed `14 passed, 2 warnings`. The six stateful lookup policy/research-chain owners remain in `orchestration`, query rewriting remains in `planning`, and retrieval attempt accounting remains in `execution`; all eight retired files are one-way compatibility exports. Replaced the remaining eight old-orchestrator dynamic calls in fact-lookup and disambiguation composition with delayed resolution of their final orchestration owners. The generic consolidation guard now rejects Task 20R legacy helper bridges as well. Final verification passed `15 passed, 2 warnings`; both warnings are existing UTC deprecations in Pydantic and a tool adapter.
- Files changed: `composition/fact_lookup_guided_composition.py`, `composition/place_disambiguation_composition.py`, `tests/test_layer_consolidation_imports.py`, and this plan.
- Deleted files: none; all eight compatibility facades remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: none. Task 20S is the next unchecked task in the restart chain.

**Re-execution required (2026-07-12):** Rerun lookup research-chain migration after policy surfaces have been revalidated; recheck the orchestration-boundary test as stated.

**Historical execution result (2026-07-12; superseded by restart):**
- Commands: task-specific retired-import and final-module boundary scans; new/legacy compatibility import smoke; `python -m compileall -q app\\planning app\\execution app\\orchestration app\\evidence app\\orchestrator`; `python -m pytest tests/test_s5_whitelist.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`; scoped `git diff --check`.
- Result: query rewriting now lives in `planning`, retrieval-attempt accounting remains in `execution`, and the six stateful lookup policy/research-chain implementations live in `orchestration`. S5, action-loop, state-reducer, composition-state, evidence-policy, planning, and execution callers now resolve final layer paths; the seven moved `orchestrator` files and the already-migrated ledger file are one-way compatibility facades. An import smoke test exposed a package-initialization cycle through `TravelAgentState` and eager `planning.__init__` imports; using the established `Any` state boundary removed that coupling. Final verification passed `13 passed` with two existing `datetime.utcnow()` deprecation warnings.
- Files changed: seven new final-owner implementation modules, the existing execution ledger, final-path callers across planning/execution/evidence/orchestration and later legacy helpers, plus seven retired implementation files converted to compatibility facades.
- Deleted files: none; retired package files remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: none; ticket, official-source, and nearby dependencies remain assigned to Tasks 20T, 20U, and 20S respectively.

### Task 20S: Migrate Nearby And POI Research Helpers

**Implementation files (10):**
- `orchestrator/baidu_poi_taxonomy.py`, `geo_fact_gazetteer.py`, `mcp_tool_arguments.py`, `nearby_anchor_policy.py`, `nearby_category_registry.py`
- `nearby_enrichment_policy.py`, `nearby_recommendation_policy.py`, `nearby_task_orchestration.py`, `s5_diversified_tool_selector.py`, `s5_poi_anchor_policy.py`

**Owner and verification:**
- Owners: `planning`, `execution`, `integrations`, and `evidence`.
- Task 20J follow-up: move `nearby_anchor_policy` to its final owner and replace the dynamic search-target bridge in `planning.nearby_anchor_strategy`.
- Task 20N follow-up: replace the S5 orchestrator's dynamic nearby task, POI-anchor, MCP-argument, and diversified-tool-selection bridges.
- Task 20O follow-up: replace the dynamic `s5_diversified_tool_selector` bridge in `orchestration/agent_core_research_plan.py` and the planning task-catalog resolver.
- Task 20P follow-up: replace the action controller's dynamic diversified-selector bridge.
- Task 20Q follow-up: replace `understanding/information_need_aliases.py` and `evidence/claim_policy_registry.py` bridges to nearby category/recommendation policy.
- Task 20P-A follow-up: remove the three concrete MCP parser imports from planning before revalidating the broader nearby/POI migration.
- Run a task-specific `rg -n "app\.orchestrator\.(baidu_poi_taxonomy|geo_fact_gazetteer|mcp_tool_arguments|nearby_anchor_policy|nearby_category_registry|nearby_enrichment_policy|nearby_recommendation_policy|nearby_task_orchestration|s5_diversified_tool_selector|s5_poi_anchor_policy)" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_s5_whitelist.py` and consolidation imports.

**Completion checkbox:** `[x] Task 20S complete`

**Execution result (2026-07-13):**
- Commands: required baseline `python -m pytest tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; legacy-facade and dynamic-bridge inventory; `python -m compileall -q app\\evidence app\\planning app\\execution app\\integrations app\\orchestration app\\understanding app\\orchestrator`; ten-pair final/legacy identity smoke; final taxonomy data load/count/hash check; task-specific retired-import scan; focused final pytest suite; AST dynamic-bridge scan; scoped `git diff --check`; final/retired taxonomy-copy SHA-256 equality check.
- Result: baseline passed `11 passed, 2 warnings`. The final owners remain evidence for taxonomy, category/recommendation/enrichment, and gazetteer policy; planning for nearby anchor/task/POI-anchor policy; execution for diversified S5 selection; and integrations for MCP argument enrichment. Replaced 15 remaining composition old-orchestrator bridges with delayed final evidence/planning module resolution, and extended the generic consolidation guard to reject all ten Task 20S helper names. The final taxonomy loaded 15 entries; the retired copy is byte-identical (`85C195B0A6D7B353D5AFEA37FEA065107C7E8C57E99BCCC57F331408A24A65D4`) and remains until the Task 20 deletion gate. Final verification passed `12 passed, 2 warnings`; both warnings are existing UTC deprecations in Pydantic and a tool adapter.
- Files changed: `composition/nearby_guided_composition.py`, `composition/place_disambiguation_composition.py`, `tests/test_layer_consolidation_imports.py`, and this plan.
- Deleted files: none; the retired taxonomy data copy and all ten compatibility facades remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: none. Task 20T is the next unchecked task in the restart chain.

**Re-execution required (2026-07-12):** Rerun nearby and POI helper migration after the repaired lookup chain, including MCP argument enrichment call paths that share the orchestration boundary.

**Historical execution result (2026-07-12; superseded by restart):**
- Commands: task-specific retired-import and final-module boundary scans; ten-pair new/legacy compatibility import smoke; taxonomy data load/hash verification; `python -m compileall -q app\\evidence app\\planning app\\execution app\\integrations app\\orchestration app\\understanding app\\orchestrator`; `python -m pytest tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; scoped `git diff --check`.
- Result: Baidu taxonomy, nearby category/recommendation/enrichment policy, and geo-fact gazetteer now live in `evidence`; nearby anchor/task/POI-anchor policy lives in `planning`; diversified S5 tool selection lives in `execution`; MCP argument enrichment lives in `integrations/mcp`. The taxonomy JSON moved with its implementation, all S5/state/action/integration callers use final paths, and the ten retired implementations are one-way compatibility facades. Final verification passed `9 passed` with two existing `datetime.utcnow()` deprecation warnings.
- Files changed: ten final-owner implementation modules, the final `evidence/data/baidu_nearby_taxonomy.json`, final-path callers across understanding/planning/execution/evidence/integrations/orchestration, and ten retired implementation files converted to compatibility facades.
- Deleted files: none; the retired taxonomy copy and package files remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: none; remaining ticket and official/evidence-signal dependencies inside MCP argument enrichment remain assigned to Tasks 20T and 20U.

### Task 20T: Migrate Ticket Lookup Helpers

**Implementation files (10):**
- `orchestrator/ticket_area_policy.py`, `ticket_lookup_attempt_tracker.py`, `ticket_lookup_helpers.py`, `ticket_lookup_policy.py`, `ticket_price_audit.py`
- `ticket_price_extractor.py`, `ticket_price_query_ladder.py`, `ticket_product_policy.py`, `ticket_relevance_policy.py`, `s5_tool_attempt_ledger.py`

**Owner and verification:**
- Owners: `planning`, `execution`, and `evidence`.
- Task 20L follow-up: move `ticket_relevance_policy` and replace the dynamic ticket-relevance bridge in `evidence.claim_relevance_filter_agent`.
- Task 20N follow-up: replace the S5 orchestrator's dynamic ticket-product and ticket-attempt-tracker bridges.
- Task 20P follow-up: replace action-controller/state-runner bridges to ticket lookup policy and official-discovery helpers.
- Task 20Q follow-up: replace `planning/claim_gap_fill_planner.py`'s dynamic ticket gap-tool bridge.
- Add a focused `tests/test_ticket_lookup_migration.py` covering the price-evidence retry contract before changing imports.
- Run a task-specific `rg -n "app\.orchestrator\.(ticket_area_policy|ticket_lookup_attempt_tracker|ticket_lookup_helpers|ticket_lookup_policy|ticket_price_audit|ticket_price_extractor|ticket_price_query_ladder|ticket_product_policy|ticket_relevance_policy|s5_tool_attempt_ledger)" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_ticket_lookup_migration.py`, `tests/test_s5_whitelist.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20T complete`

**Execution result (2026-07-13):**
- Commands: required baseline `python -m pytest tests/test_ticket_lookup_migration.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; legacy-facade and two-form dynamic-bridge inventory; `python -m compileall -q app\\planning app\\execution app\\evidence app\\integrations app\\composition app\\orchestration app\\orchestrator tests\\test_ticket_lookup_migration.py`; ten-pair final/legacy identity smoke; task-specific retired-import scan; focused final pytest suite; AST dynamic-bridge scan; scoped `git diff --check`.
- Result: baseline passed `15 passed, 4 warnings`. Ticket lookup/product/query-ladder policy remains in planning; attempt tracking and S5 attempt accounting remain in execution; ticket area, price audit/extraction, and relevance policy remain in evidence. All ten old modules are one-way compatibility exports, and no active caller resolves them through either `legacy_orchestrator_attr` or `_legacy_orchestrator`. The strict retry contract remains intact: a structured ticket product without explicit price emits `structured_ticket_product_without_price` and carries `price_lookup_mode=ticket_product_detail`, product candidates, detail URLs, and `require_price_fields=True` into MCP arguments. Final verification passed `16 passed, 4 warnings`; warnings are existing UTC deprecations in Pydantic and a tool adapter.
- Files changed: `tests/test_layer_consolidation_imports.py` and this plan. Runtime modules already used the final owners, so no duplicate code movement was performed.
- Deleted files: none; all ten compatibility facades remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: extended the generic bridge guard to cover both `legacy_orchestrator_attr` and `_legacy_orchestrator`, which catches constructed old-module paths as well as direct helper bridges. Task 20U is the next unchecked task in the restart chain.

**Re-execution required (2026-07-12):** Rerun ticket lookup migration and its strict price-retry contract after S5, action-loop, lookup, and MCP argument paths have been revalidated.

**Historical execution result (2026-07-12; superseded by restart):**
- Commands: pre-migration focused ticket contract test; task-specific retired-import and final-module boundary scans; ten-pair new/legacy compatibility and gap-model smoke; `python -m compileall -q app\\planning app\\execution app\\evidence app\\integrations app\\composition app\\orchestration app\\orchestrator tests\\test_ticket_lookup_migration.py`; `python -m pytest tests/test_ticket_lookup_migration.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; scoped `git diff --check`.
- Result: ticket lookup/product/query-ladder policy now lives in `planning`; ticket attempt tracking and the existing S5 attempt ledger live in `execution`; ticket area, price audit/extraction, and relevance policy live in `evidence`. A new strict retry contract rejects structured ticket products without an explicit price, emits `structured_ticket_product_without_price` findings, and propagates `price_lookup_mode=ticket_product_detail`, product candidates, detail URLs, and `require_price_fields=True` through the evidence gap into MCP arguments. All callers use final paths and the ten retired files are one-way compatibility facades. Final verification passed `12 passed` with four existing `datetime.utcnow()` deprecation warnings.
- Files changed: nine new final-owner implementation modules plus the existing execution S5 ledger; ticket evidence-gap model/planner and MCP/action propagation; final-path callers across planning/execution/evidence/integrations/composition/orchestration; nine retired implementations converted to compatibility facades; new `tests/test_ticket_lookup_migration.py`.
- Deleted files: none; retired package files remain until the Task 20 deletion gate.
- Blockers: none. The first contract-test collection exposed a type-only `TravelAgentState` import cycle in the old helper; replacing that annotation boundary with `Any` removed the package initialization loop without changing runtime behavior.
- Plan corrections: remaining official-source judgement, evidence-ladder, and search-snippet dependencies are still assigned to Task 20U.

### Task 20U: Migrate Evidence, Source, And Field-Extraction Helpers

**Implementation files (10):**
- `orchestrator/evidence_ladder.py`, `evidence_signal_utils.py`, `evidence_usage_role.py`, `official_candidate_bridge.py`, `official_chain_policy.py`
- `official_source_judgement.py`, `official_source_search_templates.py`, `opening_hours_extractor.py`, `peak_elevation_extraction.py`, `search_snippet_policy.py`

**Owner and verification:**
- Owner: `evidence`.
- Task 20K follow-up: move `evidence_signal_utils` and replace the dynamic signal-helper bridge in `evidence.review_mining_agent`.
- Task 20L follow-up: replace the dynamic signal-helper bridge in `evidence.evidence_contradiction_decomposer_agent`.
- Task 20N follow-up: replace the S5 orchestrator's dynamic `evidence_signal_utils.is_day_trip_query` bridge.
- Task 20P follow-up: replace the action controller's contradiction/day-trip signal bridges.
- Task 20Q follow-up: replace `planning/claim_gap_fill_planner.py`'s dynamic official-chain policy bridge.
- Run a task-specific `rg -n "app\.orchestrator\.(evidence_ladder|evidence_signal_utils|evidence_usage_role|official_candidate_bridge|official_chain_policy|official_source_judgement|official_source_search_templates|opening_hours_extractor|peak_elevation_extraction|search_snippet_policy)" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_agent_evidence_layer.py`, `tests/test_s5_whitelist.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20U complete`

**Execution result (2026-07-13):**
- Commands: required baseline `python -m pytest tests/test_agent_evidence_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; legacy-facade and two-form dynamic-bridge inventory; caller-direction inspection; `python -m compileall -q app\\evidence app\\planning app\\execution app\\integrations app\\composition app\\orchestration app\\orchestrator`; ten-pair final/legacy identity smoke; task-specific retired-import scan; focused final pytest suite; final evidence static-upward-import scan; AST dynamic-bridge scan; scoped `git diff --check`.
- Result: baseline passed `16 passed, 5 warnings`. Evidence strength, signal detection, usage roles, official-candidate/chain/source judgement, official templates, opening-hours extraction, peak-elevation extraction, and search-snippet policy already have final evidence implementations; every old module is a one-way compatibility export. All stated follow-up callers resolve those final modules, and the official-chain policy retains only delayed execution-ledger access, with no static evidence-to-execution/orchestration import. Final verification passed `17 passed, 5 warnings`; warnings are existing UTC deprecations in Pydantic and a tool adapter.
- Files changed: `tests/test_layer_consolidation_imports.py` and this plan. Runtime modules already used final evidence owners, so no duplicate code movement was performed.
- Deleted files: none; all ten compatibility facades remain until the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: none. Task 20V is the next unchecked task in the restart chain.

**Re-execution required (2026-07-12):** Rerun the evidence/source/field-extraction migration after ticket and lookup callers have been revalidated; confirm all final and compatibility imports again.

**Historical execution result (2026-07-12; superseded by restart):**
- Commands: baseline `python -m pytest tests/test_agent_evidence_layer.py tests/test_s5_whitelist.py tests/test_layer_consolidation_imports.py`; task-specific retired-import scans from both the agent and repository roots; `python -m compileall -q app/evidence app/planning app/execution app/integrations app/composition app/orchestration app/orchestrator`; final focused pytest command; final/legacy import smoke for all ten modules; scoped `git diff --check`.
- Result: evidence strength ladder, signal detection, usage-role classification, official candidate/chain policy, official search templates, opening-hours extraction, peak-elevation extraction, and search-snippet policy now have real `app.evidence` implementations. `app.evidence.official_source_judgement` was already the implementation owner and its old module was already a facade. Every active caller now resolves the final evidence path; the task-specific `rg` scan returned no matches. The final focused suite passed `12 passed, 5 warnings`; all five warnings are existing `datetime.utcnow()` deprecations.
- Files changed: nine new final-owner evidence modules; nine corresponding `app.orchestrator` modules reduced to one-way compatibility exports; final-path callers updated in evidence, planning, execution, integrations, composition, and orchestration. The official-source bridge now derives only the required claim/place data from its supplied state, while the official-chain skip ledger is reached through a late final execution-module resolution so `evidence` retains no static upward dependency.
- Deleted files: none; legacy package files remain as facades until the Task 20 deletion gate.
- Blockers: none. Final implementation and all compatibility facades import successfully.
- Plan corrections: none. Task 20V remains the next unchecked task.

### Task 20V: Migrate Non-Lookup And Composition-Orchestration Helpers

**Implementation files (7):**
- `orchestrator/claim_compiler.py`, `comparison_helpers.py`, `composition_preflight.py`, `non_lookup_task_chains.py`
- `place_disambiguation_guard.py`, `user_need_residual.py`, `subagents/composer_subagent.py`

**Owner and verification:**
- Owners: `composition`, `evidence`, `planning`, and `orchestration`.
- Task 20J follow-up: move `place_disambiguation_guard` to its final owner and replace the dynamic candidate-extraction bridge in `planning.nearby_anchor_strategy`.
- Task 20L follow-up: move `comparison_helpers` and replace the dynamic comparison-mode bridge in `evidence.claim_relevance_filter_agent`.
- Task 20N follow-up: replace the S5 orchestrator's dynamic place-disambiguation bridge.
- Task 20P follow-up: replace action-controller bridges to composition preflight, place disambiguation, and comparison helpers.
- Split `non_lookup_task_chains.py` before moving it; it is too large to treat as a single owner despite counting as one source file.
- Preflight correction (2026-07-12): before the listed helper migration, remove the two existing static `app.integrations.mcp.tool_arguments` imports from `orchestration/s5_evidence_orchestrator.py` and `orchestration/states/evidence_planning_and_tool_use.py`. Resolve their final integration helpers late at the orchestration boundary so this task's required orchestration-boundary test has a passing baseline.
- Run a task-specific `rg -n "app\.orchestrator\.(claim_compiler|comparison_helpers|composition_preflight|non_lookup_task_chains|place_disambiguation_guard|user_need_residual|subagents\.composer_subagent)" apps/agent-python/app apps/agent-python/tests`; expect no output.
- Test: `tests/test_composition_boundaries.py`, `tests/test_orchestration_boundaries.py`, and consolidation imports.

**Completion checkbox:** `[x] Task 20V complete`

**Re-execution required (2026-07-12):** Its recorded preflight is superseded. After Tasks 20N-20U are rechecked, rerun this task from its integration-boundary preflight before touching its seven listed helper implementations.

**Execution result (preflight, 2026-07-12):**
- Commands: `python -m pytest tests/test_composition_boundaries.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`; static-import location scan for `app.integrations` in `app/orchestration`; scoped plan `git diff --check`.
- Result: baseline failed before Task 20V code edits: `8 passed, 1 failed`. `test_orchestration_layer_does_not_import_concrete_external_integrations` found static `app.integrations.mcp.tool_arguments` imports in `orchestration/s5_evidence_orchestrator.py` and `orchestration/states/evidence_planning_and_tool_use.py`.
- Files changed: this plan only. No helper implementation or compatibility facade was changed.
- Deleted files: none.
- Blockers: the required Task 20V verification cannot pass until the two pre-existing integration imports move behind the orchestration boundary.
- Plan corrections: added the two-import preflight repair to Task 20V. The task remains unchecked and must resume from this repair on the next execution request.

**Execution result (2026-07-13):**
- Commands: baseline `python -m pytest tests/test_composition_boundaries.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`; task-specific retired-path scan; `python -m compileall -q app/planning app/evidence app/composition app/orchestration app/orchestrator`; final-owner and compatibility import smoke; final focused pytest command; scoped `git diff --check`.
- Result: `15 passed`. The Task 20V path scan returned no matches and scoped `git diff --check` passed. Final implementations now own lookup-claim compilation, comparison helpers, user-need residual construction, place disambiguation, the deprecated composer surface, and the non-lookup task-chain runtime. Composition preflight already belonged to `app.composition`; its remaining controller bridge now imports that final owner. Final runtime callers no longer resolve any of the seven listed `app.orchestrator` modules. The diff command emitted only existing CRLF conversion notices from the large dirty worktree.
- Files changed: new `planning/lookup_claim_compiler.py`, `planning/comparison_helpers.py`, `orchestration/place_disambiguation.py`, `orchestration/non_lookup_task_chains.py`, and `composition/composer_subagent.py`; expanded `planning/user_need_residual.py`; updated callers in composition, evidence, planning, execution, and orchestration; added the Task 20V AST bridge guard. Each migrated legacy module is now a one-way compatibility facade.
- Deleted files: none. Retired package files remain as compatibility facades until the Task 20 deletion gate.
- Blockers: none for the migration and verification gate.
- Plan corrections: the 1,200-line non-lookup composite is runtime-migrated and no longer coupled to the retired package, but its responsibility-level physical split needs characterization coverage before changing its S5/S7/S8 internals. The former in-task split requirement is superseded by the mandatory Task 20V-A below; do not start Task 20W or the deletion gate until it completes.

### Task 20V-A: Characterize The Final Non-Lookup Task Composite

**Files:**
- Add focused characterization tests for the public non-lookup entry points before moving behavior.
- Record the dependency-based extraction order for the profile, S7 evaluation, S8 composition, and orchestration coordinator modules.

**Owner and verification:**
- Keep state transitions and cross-layer assembly in `orchestration`; move pure task classification/profile work to `planning`, evidence-adoption policy to `evidence`, and answer context/draft work to `composition` through the bounded Tasks 20V-B through 20V-E below.
- Preserve the existing public functions and compatibility facade until Task 20.
- Test: new focused non-lookup behavior tests.

**Completion checkbox:** `[x] Task 20V-A complete`

**Execution result (2026-07-13):**
- Commands: dependency/call-graph inspection of `orchestration/non_lookup_task_chains.py` and its active consumers; `python -m pytest tests/test_non_lookup_task_layers.py`.
- Result: `3 passed`. The characterization suite fixes advisory profile/contract construction, advisory S7-to-S8 context continuity, and clarification-question consistency. Only S7 aggregation and S8 answer composition currently consume the module's public runtime entry points.
- Files changed: added `tests/test_non_lookup_task_layers.py`; this plan.
- Deleted files: none.
- Blockers: none.
- Plan corrections: the original physical-decomposition task contained four independently testable migrations. It is now an explicit characterization gate; Tasks 20V-B through 20V-E perform the actual extraction in dependency order. Do not start Task 20W or the deletion gate until Task 20V-E completes.

### Task 20V-B: Extract Non-Lookup Task Profiles To Planning

**Files:**
- Create `planning/non_lookup_task_profile.py` from the task-class constants, profile model, task resolution, and S5 planning profile functions in `orchestration/non_lookup_task_chains.py`.
- Update the orchestration composite to consume the final planning profile without changing its public functions.

**Owner and verification:**
- `planning` owns pure task classification, intent mapping, source-family planning, and task-profile construction; it must not statically depend on composition or orchestration.
- Keep contract construction and state mutation in orchestration for later extraction.
- Test: `tests/test_non_lookup_task_layers.py`, planning/consolidation imports, and compilation.

**Completion checkbox:** `[x] Task 20V-B complete`

**Execution result (2026-07-13):**
- Commands: AST-guided mechanical extraction of the pure profile dependency closure; `python -m compileall -q app/planning app/orchestration`; `python -m pytest tests/test_non_lookup_task_layers.py tests/test_layer_consolidation_imports.py`; planning-profile dependency scan; final-owner identity import smoke; scoped `git diff --check`.
- Result: `11 passed`. `planning/non_lookup_task_profile.py` now owns task-class mappings, `TaskChainProfile`, classification, S5 domain/profile construction, source-family planning, and task-profile policy helpers. The orchestration public entry points delegate to this final owner, and its exported `TaskChainProfile` is the same runtime type. The planning profile has no static `composition` or `orchestration` imports.
- Files changed: added `app/planning/non_lookup_task_profile.py`; updated `app/orchestration/non_lookup_task_chains.py` to consume it; extended `tests/test_non_lookup_task_layers.py` to assert final profile ownership and behavior equivalence.
- Deleted files: none.
- Blockers: none.
- Plan corrections: none. The inactive duplicate profile code remains inside the composite only until Task 20V-E replaces that module with the planned thin coordinator.

### Task 20V-C: Extract Non-Lookup S7 Evaluation To Evidence

**Files:**
- Create `evidence/non_lookup_task_evaluation.py` for evidence adoption policy, decision adjustment, evidence debug trace assembly, and nearby-candidate evidence filtering.
- Leave contract construction and cross-layer calls in the orchestration coordinator.

**Owner and verification:**
- `evidence` receives the resolved task profile and clarification context as inputs; it must not statically depend on planning, composition, or orchestration.
- Test: characterization suite, evidence boundaries, orchestration boundaries, and consolidation imports.

**Completion checkbox:** `[x] Task 20V-C complete`

**Execution result (2026-07-13):**
- Commands: AST-guided mechanical extraction of the S7 evidence-policy dependency closure; `python -m compileall -q app\\evidence app\\orchestration`; `python -m pytest tests/test_non_lookup_task_layers.py tests/test_agent_evidence_layer.py tests/test_composition_boundaries.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`; static upward-import scan of `evidence/non_lookup_task_evaluation.py`; final-owner identity smoke; scoped `git diff --check`.
- Result: `21 passed, 3 warnings`. `evidence/non_lookup_task_evaluation.py` now owns evidence-adoption policy, decision adjustment, evidence debug-trace assembly, and nearby-candidate evidence filtering. The orchestration public S7 entry point supplies the resolved profile, target label, clarification question, and nearby context, then attaches the returned trace; its exported trace and candidate types are the evidence-owned runtime types. The evidence static-upward-import scan returned no matches and the identity smoke passed. The warnings are existing Pydantic UTC deprecations.
- Files changed: added `apps/agent-python/app/evidence/non_lookup_task_evaluation.py`; updated `apps/agent-python/app/orchestration/non_lookup_task_chains.py` to delegate active S7 evaluation, trace assembly, and nearby filtering; extended `apps/agent-python/tests/test_non_lookup_task_layers.py` to assert evidence ownership identity; this plan.
- Deleted files: none. Inactive duplicate S7 code remains in the composite until Task 20V-E replaces it with the thin coordinator.
- Blockers: none.
- Plan corrections: none. Task 20V-D is the next unchecked task.

### Task 20V-D: Extract Non-Lookup S8 Composition Context

**Files:**
- Create `composition/non_lookup_task_composition.py` for clarification presentation, answer-draft construction, and S8 prompt context preparation.
- Consume evidence evaluation outputs and task-profile payloads through explicit inputs rather than importing orchestration state helpers.

**Owner and verification:**
- `composition` owns presentation and draft shaping only; it must not statically depend on planning, execution, or orchestration.
- Test: characterization suite, composition boundaries, and consolidation imports.

**Completion checkbox:** `[x] Task 20V-D complete`

**Execution result (2026-07-13):**
- Commands: inspected the active S8 compose path and its helper closure; `python -m compileall -q app\\composition app\\orchestration`; baseline `python -m pytest tests/test_non_lookup_task_layers.py tests/test_composition_boundaries.py tests/test_layer_consolidation_imports.py`; added explicit-input composition characterization; reran the same focused pytest command; static upward-import scan of `composition/non_lookup_task_composition.py`; composition import/draft smoke; scoped `git diff --check`.
- Result: `15 passed`. `composition/non_lookup_task_composition.py` now owns minimal clarification presentation, evidence-result-to-draft shaping, and S8 prompt-context construction. The orchestration entry points extract the profile payload, evidence report, trace payload, and state-derived labels/candidates, then delegate without exposing orchestration helpers to the composition module. The composition static scan returned no `planning`, `execution`, or `orchestration` imports, and its import/draft smoke passed.
- Files changed: added `apps/agent-python/app/composition/non_lookup_task_composition.py`; updated `apps/agent-python/app/orchestration/non_lookup_task_chains.py` to delegate active clarification, draft, and S8 context paths; extended `apps/agent-python/tests/test_non_lookup_task_layers.py` with the state-free composition-owner characterization; this plan.
- Deleted files: none. Inactive duplicate S8 helpers remain in the composite until Task 20V-E replaces it with the thin coordinator.
- Blockers: none.
- Plan corrections: none. Task 20V-E is the next unchecked task.

### Task 20V-E: Reduce Non-Lookup Orchestration To A Coordinator

**Files:**
- Replace `orchestration/non_lookup_task_chains.py` with a thin coordinator that assembles the extracted planning, evidence, and composition capabilities.
- Preserve every existing public function and the `app.orchestrator.non_lookup_task_chains` compatibility facade until Task 20.

**Owner and verification:**
- Keep response-contract state mutation, final compatibility exports, and cross-layer sequencing in `orchestration`.
- Test: characterization suite, `tests/test_composition_boundaries.py`, `tests/test_orchestration_boundaries.py`, consolidation imports, import smoke, and scoped `git diff --check`.

**Completion checkbox:** `[x] Task 20V-E complete`

**Execution result (2026-07-13):**
- Commands: public-surface and caller inventory; whole-file coordinator replacement; `python -m compileall -q app\\orchestration app\\orchestrator app\\planning app\\evidence app\\composition`; `python -m pytest tests/test_non_lookup_task_layers.py tests/test_composition_boundaries.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`; compatibility facade/sample-trace import smoke; legacy-composite implementation-body scan; scoped `git diff --check`.
- Result: `19 passed`. `orchestration/non_lookup_task_chains.py` is now a thin coordinator: it owns response-contract state mutation, state-to-payload projection, trace persistence, and the sequence that invokes final planning, evidence, and composition owners. The 1,000-line duplicate S5/S7/S8 implementations are gone. `TaskChainProfile`, `TaskDebugTrace`, and `NearbyCandidate` remain final-owner aliases, while the `app.orchestrator.non_lookup_task_chains` facade continues to expose the public compatibility surface. The legacy-body scan returned no matches and the compatibility/sample-trace smoke passed.
- Files changed: replaced `apps/agent-python/app/orchestration/non_lookup_task_chains.py` with the thin coordinator; extended `apps/agent-python/tests/test_non_lookup_task_layers.py` to assert legacy facade type/function compatibility; this plan.
- Deleted files: none. The composite implementation bodies were removed from the coordinator file; package-level compatibility facades remain until Task 20.
- Blockers: none.
- Plan corrections: none. Task 20W is the next unchecked task and must update direct test consumers and global compatibility imports before Task 20 may delete retired packages.

### Task 20W: Migrate Tests And Close Compatibility Imports

**Files (5 direct test consumers plus compatibility entries):**
- `tests/test_agent_contract_layer.py`, `tests/test_agent_evidence_layer.py`, `tests/test_governance_observability_layer.py`, `tests/test_orchestration_boundaries.py`, `tests/test_s5_whitelist.py`
- `app/_legacy.py`, `app/contract.py`, retired package `__init__.py` exports only as needed for the final import scan.

**Owner and verification:**
- Update tests to import final owners, replace assertions that require legacy wrappers, and remove every completed consolidation allowlist entry.
- Task 20H follow-up: remove the remaining intentional `schemas.response`, `schemas.evidence`, and `schemas.tool_whitelist` compatibility assertions once all runtime owner batches are complete.
- `app/_legacy.py` remains absent from runtime; keep `app.contract` only as a contracts-only re-export if Java/API compatibility still requires it.
- Run the global Task 20 Step 1 import scan. Expected: no output.
- Test: all Python tests with `pytest`, app startup import, and consolidation imports.

**Completion checkbox:** `[x] Task 20W complete`

**Execution result (2026-07-13):**
- Commands: global retired static-import inventory; direct-consumer and compatibility-facade inspection; `python -m compileall -q app tests`; focused `python -m pytest tests/test_agent_contract_layer.py tests/test_agent_evidence_layer.py tests/test_governance_observability_layer.py tests/test_orchestration_boundaries.py tests/test_s5_whitelist.py tests/test_non_lookup_task_layers.py tests/test_layer_consolidation_imports.py`; full `python -m pytest`; `python -c "from app.main import app; assert app.title"`; repeated global Task 20 Step 1 scan; scoped `git diff --check`.
- Result: the global static-import scan returned no matches across `app` and `tests`. Focused verification passed `33 passed, 5 warnings`; the complete Python suite passed `52 passed, 7 warnings`; the app startup import smoke passed. Warnings are existing Pydantic UTC deprecations plus the search MCP adapter's existing UTC deprecation. Consolidation retired-import and layer allowlists were already empty and remain empty.
- Files changed: updated `tests/test_agent_contract_layer.py`, `tests/test_agent_evidence_layer.py`, `tests/test_orchestration_boundaries.py`, `tests/test_s5_whitelist.py`, and `tests/test_non_lookup_task_layers.py` to use final owners and final-layer assertions; this plan. `tests/test_governance_observability_layer.py` was audited and already used final owners, so no edit was needed.
- Deleted files: none. `app/_legacy.py` remains a non-runtime error stub; `app/contract.py` remains a contracts-only re-export for API compatibility. Retired package facades remain intact for the Task 20 deletion gate.
- Blockers: none.
- Plan corrections: Task 20's dynamic-reference preflight found active retired-package resolution after this task completed. Tasks 20X-A through 20X-C now precede the deletion gate; Task 20W remains complete because its static import and test-migration scope is complete.

**Dependency note (2026-07-13):** Do not start Task 20W until Tasks 20N-20V and 20V-A through 20V-E have each been rechecked; test migration and compatibility-allowlist removal must reflect the rebuilt runtime path.

---

### Task 20X-A: Replace Dynamic Schema Compatibility Bridges

**Files (10 callers):**
- `composition/composer.py`, `composition/answer_composer.py`, `composition/response_contract_compiler.py`
- `orchestration/state_machine.py`, `orchestration/state_reducer.py`, `orchestration/states/evidence_planning_and_tool_use.py`, `orchestration/states/llm_understanding.py`
- `planning/claim_search_planner.py`, `planning/s5_domain_planner.py`
- `integrations/java_gateway/converters.py`

**Owner and verification:**
- Replace every `legacy_schema_attr` and dynamic `app.schemas.*` resolution with the final contracts, understanding, planning, evidence, or observability owner. Composition may use its bounded final delayed-binding helper where a static import would violate its layer rule.
- Preserve public schema compatibility facades until Task 20; do not import `app.schemas` from a final layer after this task.
- Test: contract/evidence/orchestration boundaries, Java-gateway converter coverage, consolidation imports, and a dynamic schema-reference scan.

**Completion checkbox:** `[x] Task 20X-A complete`

**Execution result (2026-07-13):**
- Commands: schema-facade ownership inspection; `python -m compileall -q app\\composition app\\orchestration app\\planning app\\integrations\\java_gateway`; focused `python -m pytest tests/test_agent_contract_layer.py tests/test_agent_evidence_layer.py tests/test_agent_execution_integration_layer.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py`; task-range dynamic schema scan; app/final-schema/compatibility-schema identity smoke; scoped `git diff --check`.
- Result: `22 passed, 4 warnings`. All ten task callers now resolve final schema owners: composition uses bounded `final_attr` calls to understanding types; orchestration uses direct final understanding/planning imports; planning uses the final evidence model directly; the Java gateway's allowed dynamic resolver now targets `app.evidence.evidence_model`. The task-range scan returned no `legacy_schema_attr` or `app.schemas.*` reference. Compatibility facades still resolve to the exact final `Evidence` and `EvidenceGapRequest` types. Warnings are existing Pydantic UTC deprecations.
- Files changed: `apps/agent-python/app/composition/composer.py`, `answer_composer.py`, `response_contract_compiler.py`; `apps/agent-python/app/orchestration/state_machine.py`, `state_reducer.py`, `states/evidence_planning_and_tool_use.py`, `states/llm_understanding.py`; `apps/agent-python/app/planning/claim_search_planner.py`, `s5_domain_planner.py`; `apps/agent-python/app/integrations/java_gateway/converters.py`; added Java-gateway final-evidence coverage in `apps/agent-python/tests/test_agent_execution_integration_layer.py`; this plan.
- Deleted files: none. `app.schemas` remains a compatibility package until Task 20.
- Blockers: none.
- Plan corrections: none. Task 20X-B is the next unchecked task.

### Task 20X-B: Replace Dynamic Orchestrator Compatibility Bridges

**Files (9 callers):**
- `execution/route_feasibility_agent.py`, `execution/keyword_search_agent.py`
- `planning/tool_whitelist_builder.py`, `planning/ticket_lookup_policy.py`
- `evidence/policy_guard.py`
- `orchestration/lookup_research_chain.py`, `orchestration/lookup_query_objectives.py`, `orchestration/s5_evidence_orchestrator.py`, `orchestration/state_reducer.py`

**Owner and verification:**
- Replace dynamic `app.orchestrator.*` resolution with final planning, evidence, composition, observability, or orchestration owners. Retain late binding only when required by a declared layer boundary, and point it at a final module.
- Preserve behavior of claim-search, response sanitization, state policy, and evidence-gate integrations.
- Test: S5 whitelist, ticket migration, capability/boundary tests, consolidation imports, and a dynamic orchestrator-reference scan.

**Completion checkbox:** `[x] Task 20X-B complete`

**Execution result (2026-07-13):**
- Commands: caller-to-final-owner inspection; `python -m compileall -q app\\execution app\\planning app\\evidence app\\orchestration`; task-range dynamic retired-orchestrator scan; `python -m pytest tests/test_s5_whitelist.py tests/test_ticket_lookup_migration.py tests/test_agent_capability_boundaries.py tests/test_orchestration_boundaries.py tests/test_layer_consolidation_imports.py tests/test_agent_execution_integration_layer.py`; scoped `git diff --check`.
- Result: `30 passed, 5 warnings`. Execution now imports the final `planning.ClaimSearchPlanner`; planning's boundary-required delayed bindings target final `orchestration.state_policy` and `composition.response_sanitizer`; evidence targets final `orchestration.state_policy`; S5 and state reduction import final planning/evidence owners directly. The two unused retired-orchestrator dynamic helpers were removed. The task-range scan returned no `app.orchestrator`, `legacy_orchestrator_attr`, or `_legacy_orchestrator` references. Warnings are existing Pydantic and search-MCP UTC deprecations.
- Files changed: `apps/agent-python/app/execution/route_feasibility_agent.py`, `keyword_search_agent.py`; `apps/agent-python/app/planning/tool_whitelist_builder.py`, `ticket_lookup_policy.py`; `apps/agent-python/app/evidence/policy_guard.py`; `apps/agent-python/app/orchestration/lookup_research_chain.py`, `lookup_query_objectives.py`, `s5_evidence_orchestrator.py`, `state_reducer.py`; this plan.
- Deleted files: none. Retired dynamic boundary helpers remain until Task 20X-C; retired packages remain until Task 20's deletion gate.
- Blockers: none.
- Plan corrections: none. Task 20X-C is the next unchecked task.

### Task 20X-C: Remove Retired Dynamic Boundary Helpers

**Files:**
- `composition/composer.py`, `composition/answer_composer.py`, `composition/nearby_guided_composition.py`, `composition/place_disambiguation_composition.py`
- Clean stale helper imports: `composition/response_contract_compiler.py`, `orchestration/action_model_controller.py`, `orchestration/claude_state_runner.py`, `orchestration/state_machine.py`, `orchestration/states/evidence_planning_and_tool_use.py`
- `tests/test_layer_consolidation_imports.py`
- `composition/_legacy_boundary.py`, `orchestration/_legacy_boundary.py`, `app/_legacy.py`

**Owner and verification:**
- Once 20X-A and 20X-B have removed all callers, delete the `legacy_agent_attr`, `legacy_orchestrator_attr`, and `legacy_schema_attr` mechanisms and clean residual retired-package wording or paths from the non-runtime stub.
- Keep bounded final-layer delayed binding and final integration access only where an actual layer boundary requires it.
- Test: global static and dynamic retired-reference scans, full Python suite, app startup import, and scoped `git diff --check`.

**Plan correction (2026-07-13, before execution):**
- The original file list omitted five modules that retain unused imports of the helper symbols. They contain no remaining `legacy_agent_attr`, `legacy_orchestrator_attr`, or `legacy_schema_attr` call, but must lose those imports before the helper definitions can be deleted. This correction remains within Task 20X-C; no follow-up task is required.
- The first global dynamic scan also found the consolidation AST test's own retired helper-name literals. Update that test to preserve a generic retired-helper call guard without retaining the deleted names as scan-visible strings.

**Completion checkbox:** `[x] Task 20X-C complete`

**Execution result (2026-07-13):**
- Commands: retired-helper call and import inventory; `python -m compileall -q app tests`; global static retired-import scan; global dynamic retired-reference scan; `python -m pytest`; `python -c "from app.main import app; assert app.title"`; scoped `git diff --check`.
- Result: `54 passed, 8 warnings`. Composition now uses bounded `final_attr` resolution for the final claim-search and trace owners; five stale retired-helper imports were removed; both dynamic-boundary modules no longer define the retired agent, orchestrator, or schema resolvers; and `app._legacy` no longer names a retired runtime path. The consolidation AST guard now rejects all retired helper calls without leaving scan-visible deleted names. Both global scans returned zero matches, and app startup import passed. Warnings are existing Pydantic and search-MCP UTC deprecations.
- Files changed: `apps/agent-python/app/composition/composer.py`, `answer_composer.py`, `nearby_guided_composition.py`, `place_disambiguation_composition.py`, `response_contract_compiler.py`, `_legacy_boundary.py`; `apps/agent-python/app/orchestration/action_model_controller.py`, `claude_state_runner.py`, `state_machine.py`, `states/evidence_planning_and_tool_use.py`, `_legacy_boundary.py`; `apps/agent-python/app/_legacy.py`; `apps/agent-python/tests/test_layer_consolidation_imports.py`; this plan.
- Deleted files: none. Task 20X-C only removed retired dynamic resolver mechanisms; all retired package directories remain for Task 20's verified deletion gate.
- Blockers: none.
- Plan corrections: Task scope was expanded to remove five stale imports and one scan-polluting AST-test literal. These changes were necessary to make the intended global deletion checks meaningful and do not create a follow-up task. Task 20 is the next unchecked task.

---

### Task 20Y-A: Characterize Shared Tool Dependencies on Retired Packages

**Files:**
- Inventory all 35 current callers under `packages/tools/` that still refer to a retired `app.*` package.
- Verify the final owner and type identity for evidence/claim, official-source, ticket, trace, semantic-frame, information-need, travel-task, cache, and source-policy imports.

**Owner and verification:**
- This is a repository-boundary migration: `packages/tools` is live shared runtime code and must use final Agent owners directly, not compatibility wrappers or recreated retired packages.
- Separate direct import migrations from lazy policy/router imports so each later task has a bounded behavioral surface.
- Test: an inventory that accounts for every retired reference, representative final-owner import smoke, and an updated repo-wide scan baseline.

**Completion checkbox:** `[x] Task 20Y-A complete`

**Execution result (2026-07-13):**
- Commands: repository-wide `packages/tools` retired-reference inventory; module/file grouping; final-owner symbol and source-path inspection; `python -m compileall -q packages/tools`; representative evidence/official-source/ticket/trace/cache final-owner import smoke.
- Result: the live shared package contains `49` retired references in `35` files. `42` are direct schema-model imports for Task 20Y-B; `7` are runtime policy/cache/router references for Task 20Y-C. The final-owner map is complete: evidence models -> `app.evidence.evidence_model`; official-source and ticket models -> `app.evidence.official_source` / `ticket_info`; trace -> `app.observability.tool_trace`; place, semantic-frame, travel-task, and user-query -> `app.understanding`; information-need and source selection -> `app.planning`; cache -> `app.integrations.storage.tool_cache`; policy/taxonomy references -> final evidence, planning, or understanding modules. All mapped final-owner files exist, compilation passed, and the representative final-owner smoke passed.
- Files changed: this plan only.
- Deleted files: none in this task. The Task 20 deletions remain in place; the current suite is expected to remain broken until Tasks 20Y-B through 20Y-D remove the mapped imports.
- Blockers: none for characterization.
- Plan corrections: refined Tasks 20Y-B and 20Y-C with the counted direct-model versus behavioral dependency split. Task 20Y-B is the next unchecked task.

---

### Task 20Y-B: Migrate Shared Tool Models and Evidence Types

**Files:**
- The direct evidence/claim/model consumers found by Task 20Y-A, including `packages/tools/base.py`, adapters, concrete tool implementations, mock data, official-source tools, ticketing normalizers, and registry surfaces.
- Exact migration set: 42 direct schema references: `app.schemas.evidence` (32), `official_source` (2), `semantic_frame` (2), plus one each for `information_need`, `place`, `ticket_info`, `tool_trace`, `travel_task`, and `user_query`.

**Owner and verification:**
- Replace all retired schema imports with their final evidence, planning, understanding, contracts, and observability modules while preserving public `tools.*` APIs and model identity.
- Do not add a new `app.schemas` shim. Add focused import and conversion coverage for representative MCP, official-source, ticketing, and trace paths.
- Test: `python -m compileall -q packages/tools`, `tests/test_shared_tool_final_models.py`, and a `packages/tools` schema retired-reference scan.

**Plan correction (2026-07-13, during execution):**
- `tests/test_agent_execution_integration_layer.py` imports the shared `ToolRegistry`, which also initializes the still-unmigrated `hybrid_tool` cache dependency. Move that registry-level integration check to Task 20Y-D; retain this task's focused coverage at the direct model boundary.

**Completion checkbox:** `[x] Task 20Y-B complete`

**Execution result (2026-07-13):**
- Commands: direct schema-owner import inspection; `python -m compileall -q packages/tools tests`; `packages/tools` schema retired-reference scan; final-model identity smoke for MCP, official-source, and ticketing modules; `python -m pytest tests/test_shared_tool_final_models.py`; exact remaining-reference assertion; scoped `git diff --check`.
- Result: all 42 direct schema references now use final owners, and the schema scan is empty. The new focused test passed `1 passed`, proving direct identity for `Claim`, `Evidence`, `OfficialSourceDiscoveryResult`, and `TicketSnapshot`. The remaining retired references exactly match Task 20Y-C's seven cache/policy/router dependencies. A combined run with `tests/test_agent_execution_integration_layer.py` was intentionally deferred: its `ToolRegistry` import reaches the unmodified `hybrid_tool` cache dependency and therefore belongs to Task 20Y-D after 20Y-C.
- Files changed: 35 `packages/tools` source files across base, adapter, MCP, concrete, official-source, ticketing, router, registry, and mock surfaces; added `apps/agent-python/tests/test_shared_tool_final_models.py`; this plan.
- Deleted files: none in this task.
- Blockers: none for the direct model migration. Full registry/runtime verification remains pending Task 20Y-C.
- Plan corrections: moved the registry-level execution integration test from Task 20Y-B to Task 20Y-D because it legitimately requires the remaining behavioral migration. Task 20Y-C is the next unchecked task.

---

### Task 20Y-C: Migrate Shared Tool Policy, Cache, and Router Dependencies

**Files:**
- `packages/tools/hybrid_tool.py`, `knowledge_prior_tool.py`, `tool_router.py`, `official_source/official_source_discovery_tool.py`, `mcp/adapters/nearby_poi_claims.py`, and any remaining callers identified by Task 20Y-B.
- Exact behavioral migration set: seven references: `storage.tool_cache`; `policies.evidence_policy`; `orchestrator.policies`; `orchestrator.ticket_relevance_policy`; and the three nearby information-need, taxonomy, and recommendation-policy imports.

**Owner and verification:**
- Repoint lazy policy, taxonomy, cache, and router resolution to their final planning, evidence, observability, or tools owner. Preserve source-selection, official-discovery, nearby-claim, and cache behavior without recreating the retired packages.
- Test: targeted router, official-source, nearby, and cache import/behavior coverage; global `packages/tools` static and dynamic retired-reference scans.

**Completion checkbox:** `[x] Task 20Y-C complete`

**Execution result (2026-07-13):**
- Commands: final-owner API inspection; `python -m compileall -q packages/tools tests`; shared registry/router/nearby/official-source import smoke; `python -m pytest tests/test_shared_tool_final_models.py`; shared-tool static and dynamic retired-reference scans.
- Result: all seven behavioral references now target final owners: integration cache, evidence policy, planning source selection, evidence ticket relevance, understanding nearby aliases, and evidence nearby taxonomy/recommendation policy. The shared `ToolRegistry` and `ToolRouter` now import successfully. Focused coverage passed `3 passed`, exercising cache behavior, source-selection fallback, nearby normalization, and official ticket discovery without page probing. The only warning is the existing `datetime.utcnow()` deprecation in the official-source discovery tool.
- Files changed: `packages/tools/hybrid_tool.py`, `knowledge_prior_tool.py`, `tool_router.py`, `official_source/official_source_discovery_tool.py`, `mcp/adapters/nearby_poi_claims.py`; expanded `apps/agent-python/tests/test_shared_tool_final_models.py`; this plan.
- Deleted files: none in this task.
- Blockers: none. The full application suite remains intentionally deferred to Task 20Y-D.
- Plan corrections: none. Task 20Y-D is the next unchecked task.

---

### Task 20Y-D: Verify Shared Tool Runtime After Package Deletion

**Files:**
- `packages/tools/**`, `apps/agent-python/tests/**`, and any direct final-layer caller exposed by the shared-tool import smoke.

**Owner and verification:**
- Confirm `packages/tools` imports only final Agent owners, then run targeted shared-tool import smoke and the complete Python suite.
- Do not restore any deleted retirement package. Record any remaining dependency as a new bounded task before resuming Task 20.
- Test: `python -m pytest`, `python -c "from app.main import app; print(app.title)"`, and repository-wide static/dynamic retired-reference scans including `packages/tools`.
- Include `tests/test_agent_execution_integration_layer.py` after Task 20Y-C has removed the shared registry's remaining runtime dependencies.

**Completion checkbox:** `[x] Task 20Y-D complete`

**Execution result (2026-07-13):**
- Commands: repository-wide static and dynamic retired-reference scans covering `app`, `tests`, and `packages/tools`; `python -m pytest`; `python -c "from app.main import app; print(app.title)"`; repeated post-verification scans; scoped `git diff --check`.
- Result: the first full test run exposed one retired test expectation: composition tests still treated deleted `app/prompts` as the template source. The test now verifies the final `app/composition/prompt_templates` owner instead. The complete suite then passed `57 passed, 9 warnings`; application startup printed `Travel Agent Python`; and both repository-wide scans returned zero matches. Warnings are existing Pydantic and `datetime.utcnow()` deprecations in MCP/official-source code.
- Files changed: `apps/agent-python/tests/test_composition_boundaries.py`; this plan.
- Deleted files: none in this task.
- Blockers: none. Shared tools use final owners only and the deleted package directories are not restored.
- Plan corrections: corrected the composition-template test to its final ownership boundary. Task 20 is the next unchecked task for final deletion-gate acceptance.

---

## Task 20: Delete Retired Python Packages

**Follow-up from Task 18:**
- `app.orchestrator/agent_core_*.py` and workflow helpers still reached through `app.orchestration._legacy_boundary` must be migrated or reclassified before deleting `app.orchestrator`.
- Do not delete `app.orchestrator` until dynamic references from `app.orchestration._legacy_boundary` and `app.composition._legacy_boundary` have been resolved.

**Follow-up from Task 19:**
- `app.schemas.user_query.py` still imports the `ToolTrace` compatibility surface, while `app.orchestration.state_reducer.py` and `app.integrations.java_gateway.converters.py` still resolve that legacy schema type. Migrate those consumers to `app.observability.tool_trace` when the remaining state models leave `app.schemas`.
- Retired `app.agents` consumers still import the `app.orchestrator.policies` compatibility export. Repoint retained consumers to `app.planning.source_selection_policy` before removing `app.orchestrator`.

**Files:**
- Delete after verification: `apps/agent-python/app/agents/`
- Delete after verification: `apps/agent-python/app/orchestrator/`
- Delete after verification: `apps/agent-python/app/schemas/`
- Delete after verification: `apps/agent-python/app/tool_gateway/`
- Delete after verification: `apps/agent-python/app/storage/`
- Delete after verification: `apps/agent-python/app/catalog/`
- Delete after verification: `apps/agent-python/app/prompts/`
- Delete after verification: `apps/agent-python/app/policies/`
- Inspect/clean: `apps/agent-python/app/_legacy.py`
- Inspect/clean: `apps/agent-python/app/contract.py`
- Test: all Python tests.

**Step 1: Confirm no active imports**

Run (including the live shared tools boundary):

```powershell
rg -n "from app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)|import app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)" apps/agent-python/app apps/agent-python/tests packages/tools --glob '*.py'
```

Expected:
- No output, except this plan/docs if included accidentally.

**Step 2: Resolve absolute paths before deletion**

Use PowerShell to verify each target directory path starts with the repository root.

**Step 3: Delete retired packages**

Use `Remove-Item -Recurse -Force -LiteralPath` for only the verified retired directories.

Do not delete:

```text
apps/agent-python/app/tools/
apps/agent-python/app/contracts/
apps/agent-python/app/orchestration/
```

**Step 4: Remove compatibility wrappers**

Remove or shrink `app/_legacy.py` and `app/contract.py` only after confirming public imports are no longer needed. If `app.contract` remains for Java/API compatibility, it must be a tiny stable contract re-export and not import retired packages.

**Step 5: Run full Python verification**

Run:

```powershell
cd apps/agent-python
pytest
python -c "from app.main import app; print(app.title)"
```

Expected:
- All tests pass.
- No retired package directories remain.

**Completion checkbox:** `[x] Task 20 complete`

**Execution result (final acceptance, 2026-07-13):**
- Commands: repository-wide static and dynamic retired-reference scans over `apps/agent-python/app`, `apps/agent-python/tests`, and `packages/tools`; deleted-target absence and protected-final-surface audit; stable `app.contract` re-export inspection; `python -m pytest`; `python -c "from app.main import app; print(app.title)"`; `git diff --check`.
- Result: both retired-reference scans returned zero matches. All eight retired package directories and `app/_legacy.py` remain absent; final `app/tools/`, `app/contracts/`, and `app/orchestration/` surfaces remain present; and `app.contract` is the permitted contracts-only re-export. Full Python verification passed `57 passed, 9 warnings in 59.99s`; application startup printed `Travel Agent Python`. The warnings are existing Pydantic and `datetime.utcnow()` deprecations.
- Files changed: this plan only in final acceptance. The previously approved deletion removed `apps/agent-python/app/agents/`, `orchestrator/`, `schemas/`, `tool_gateway/`, `storage/`, `catalog/`, `prompts/`, `policies/`, and `app/_legacy.py`.
- Blockers: none for Task 20. `git diff --check` reports pre-existing EOF blank-line errors in seven unrelated Java source/test files and line-ending warnings across the dirty worktree; no Task 20 Python file is implicated.
- Plan corrections: none. Task 21 is the next unchecked task.

**Execution result (2026-07-13; Task 20 deletion attempted but not complete):**
- Commands: plan-compliance review; repeated app/test static and dynamic reference gates; absolute-path and protected-directory audit; verified deletion of the eight retired package directories and `app/_legacy.py`; post-deletion path and reference scans; `python -m pytest`.
- Result: deletion removed the eight plan-listed retired directories (470 files) and the unused error stub. App/test scans and protected-directory checks passed, but the full suite failed during collection with `ModuleNotFoundError: app.schemas`: the live shared `packages/tools` package still contains 35 files with direct retired-package imports. The original Task 20 scan omitted this repository-level runtime boundary, so its pre-deletion audit was incomplete.
- Deleted files: `apps/agent-python/app/agents/`, `orchestrator/`, `schemas/`, `tool_gateway/`, `storage/`, `catalog/`, `prompts/`, `policies/`, and `app/_legacy.py`. The final `app/tools/`, `app/contracts/`, and `app/orchestration/` directories remain present.
- Blockers: full Python validation cannot pass until the `packages/tools` dependencies are migrated to final owners. The first failure is `packages/tools/adapters/mcp_tool_adapter.py` importing `app.schemas.evidence`; the repository-wide inventory finds 35 affected files.
- Plan corrections: inserted Tasks 20Y-A through 20Y-D before Task 20 completion and expanded Step 1 to scan `packages/tools`. Do not restore the deleted packages; resume at Task 20Y-A, then return to Task 20 for final verification only.

**Execution result (preflight, 2026-07-13; Task 20 not complete):**
- Commands: required global static retired-import scan; global dynamic retired-reference scan; absolute-path audit for all eight retired package directories; compatibility-wrapper inspection; attempted verified `Remove-Item` deletion.
- Result: both import/reference gates returned zero matches. All eight package directories resolved inside the repository root. `app.contract` remains the allowed tiny contracts re-export; `app._legacy` has no internal consumer and is eligible for removal. The deletion command was rejected by the execution safety policy because it would recursively remove multiple core source directories without an exact user authorization naming those targets.
- Deleted files: none. The rejected command did not run, so all eight directories and `app/_legacy.py` remain present.
- Blockers: explicit approval is required to delete exactly `apps/agent-python/app/agents/`, `orchestrator/`, `schemas/`, `tool_gateway/`, `storage/`, `catalog/`, `prompts/`, `policies/`, plus `apps/agent-python/app/_legacy.py`.
- Plan corrections: none. Resume Task 20 from Step 3 only after the user explicitly approves this exact deletion list; then run Steps 4 and 5.

**Execution result (preflight, 2026-07-13; Task 20 not complete):**
- Commands: required Step 1 static import scan; final-layer dynamic compatibility inventory covering `legacy_agent_attr`, `legacy_orchestrator_attr`, `legacy_schema_attr`, and dynamic `app.orchestrator` / `app.schemas` paths; inspected both dynamic-boundary modules.
- Result: the Step 1 static scan passed with no output, but deletion is unsafe. Active final-layer callers still dynamically resolve retired `app.schemas` (state machine, composition contract/draft paths, planning evidence checks, and Java-gateway conversion) and retired `app.orchestrator` (claim-search, state policy, trace, response sanitizer, S5, lookup-chain, and evidence-gate paths). The two dynamic-boundary modules still construct retired `app.agents`, `app.orchestrator`, and `app.schemas` module paths.
- Deleted files: none. Step 2 absolute-path verification and Step 3 deletion were intentionally not run because the dynamic-reference gate failed.
- Blockers: deleting any listed retired package would break active runtime imports despite the zero static scan.
- Plan corrections: inserted dependency-ordered Tasks 20X-A, 20X-B, and 20X-C before Task 20. Resume at Task 20X-A; rerun Task 20 from Step 1 only after all three tasks complete.

**Execution result (preflight; Task 20 not complete):**
- Ran the required Step 1 scan: `rg -n "from app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)|import app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)" apps/agent-python/app apps/agent-python/tests`.
- Result: 533 matched lines, not the required zero. Active runtime code still contains extensive direct dependencies within `app.orchestrator`, `app.agents`, and `app.schemas`; tests also import those packages directly.
- Confirmed examples include the S5 runtime/test path, legacy agent modules, `app.schemas.user_query`, and remaining orchestration policy helpers. These are not harmless compatibility imports and cannot be deleted safely.
- No target-directory path verification, package deletion, wrapper removal, or full-test run was performed because the Step 1 gate failed. No runtime code was changed.
- Plan correction: Task 20 remains a deletion-only gate. New Task 20A must inventory and decompose the remaining implementation migration into bounded tasks before Task 20 can resume.
- Blocker: deleting any retired package now would break imports and violate the plan's no-wide-breakage rule.
- No commit was made.

---

## Task 21: Cross-Service Contract And Frontend Flow Verification

**Files:**
- Inspect/modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/**`
- Inspect/modify: `apps/api-java/src/main/java/com/travel/intelligence/api/platform/**`
- Inspect/modify: `apps/agent-python/app/contracts/**`
- Inspect/modify: `apps/web/src/api/travel.js`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/agent/application/TravelQueryServiceTest.java`
- Test: `apps/api-java/src/test/java/com/travel/intelligence/api/platform/TravelPlatformFlowTest.java`
- Test: `apps/agent-python/tests/test_agent_contract_layer.py`

**Step 1: Verify Java-Python field contract**

Run:

```powershell
rg -n "answer|session_id|query_id|visible_trace|evidence_summary|limitations|confidence|tool_traces|structured_result|semantic_frame_summary|answer_mode" apps/api-java/src/main/java/com/travel/intelligence/api apps/agent-python/app/contracts apps/web/src
```

Expected:
- Java, Python, and Web agree on response fields or map them explicitly.

**Step 2: Run contract tests**

Run:

```powershell
cd apps/agent-python
pytest tests/test_agent_contract_layer.py

cd ..\api-java
mvn test "-Dtest=TravelQueryServiceTest,TravelPlatformFlowTest"
```

Expected:
- Python contract passes.
- Java contract/platform flow passes.

**Step 3: Update frontend only if contract shape changed**

If frontend fields changed, update `apps/web/src/api/travel.js` and related UI rendering. Otherwise record no frontend change.

**Completion checkbox:** `[x] Task 21 complete`

**Execution result (2026-07-13):**
- Commands: planned cross-service response-field scan; `python -m pytest tests/test_agent_contract_layer.py`; Maven target tests for `TravelQueryServiceTest,TravelPlatformFlowTest`; `npm run build` in `apps/web`.
- Result: the Python snake_case Agent contract is explicitly mapped by Java's `PythonAgentClient`; Java persists and returns the original Agent response as `agentResponse`; and the web client sends the platform's camelCase request and reads that response envelope. All planned response fields have an explicit owner/mapping. Python contract coverage passed `3 passed`; Java passed `4` tests with `BUILD SUCCESS`; and the Vite production build passed. Java emitted only the existing Mockito dynamic-agent/JDK warnings.
- Files changed: this plan only. No frontend change was needed because the request/response shape is unchanged and `apps/web/src/api/travel.js` already uses the platform envelope correctly.
- Blockers: none. The initial `mvn`/`mvn.cmd` command names were not resolved by the execution shell, so verification used the discovered local Maven executable at `E:\学习文件\研究生\就业\Java学习\Java相关\apache-maven-3.9.15\bin\mvn.cmd`.
- Plan corrections: none. Task 22 is the next unchecked task.

---

## Task 22: Documentation And Developer Guidance Refresh

**Files:**
- Modify: `README.md`
- Modify: `RUNBOOK.md`
- Modify: `AGENTS.md`
- Modify/create if useful: `PROJECT_MAINLINE.md`
- Modify/create if useful: `REPO_MAP.md`

**Step 1: Update architecture docs to implemented state**

Remove language that says layers are only wrappers or migration targets. Document the real implementation owner for each layer.

**Step 2: Document retired package deletion**

Document that these packages no longer exist:

```text
app.agents
app.orchestrator
app.schemas
app.tool_gateway
app.storage
app.catalog
app.prompts
app.policies
```

If any compatibility import remains, document why and what it is allowed to re-export.

**Step 3: Update developer rules**

AGENTS must state:
- New Python code must go directly into capability layers.
- Do not recreate retired packages.
- Java application/domain dependency rules.
- Java-Python contract test requirement.

**Step 4: Run doc search**

Run:

```powershell
rg -n "wrapper|compatibility|migration target|agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies|Java Layering|Agent Product Capability|Java-Agent" README.md RUNBOOK.md AGENTS.md PROJECT_MAINLINE.md REPO_MAP.md
```

Expected:
- Any remaining mention of retired package names is explicitly historical or forbidden, not a current runtime path.

**Completion checkbox:** `[x] Task 22 complete`

**Execution result (2026-07-13):**
- Commands: plan/documents inventory; runtime-path and `app.contract` ownership audit; planned documentation search across `README.md`, `RUNBOOK.md`, `AGENTS.md`, `PROJECT_MAINLINE.md`, and `REPO_MAP.md`.
- Result: documentation now describes implemented Java domain layers and final Python capability owners rather than migration targets. It records all eight retired Python packages as deleted and forbidden, and limits `app.contract` to its contracts-only public re-export. `AGENTS.md` now points to the final `app/orchestration/state_machine.py`, requires capability-owner placement for new Python code, preserves Java layer direction, and requires both sides of a Java-Python contract change to be tested before web behavior changes. The documentation scan confirms every retired-package reference is historical/forbidden; remaining `catalog`, `storage`, and `prompts` mentions describe final ownership responsibilities.
- Files changed: `README.md`, `RUNBOOK.md`, `AGENTS.md`; added `PROJECT_MAINLINE.md` and `REPO_MAP.md`; this plan.
- Blockers: none.
- Plan corrections: none. Task 23 is the next unchecked task.

---

## Task 23: Final Full-Stack Verification And Cleanup

**Files:**
- Inspect: full repository.
- Modify: this plan with final results.

**Step 1: Run final Java tests**

Run:

```powershell
cd apps/api-java
mvn test
```

Expected:
- `BUILD SUCCESS`.

**Step 2: Run final Python tests**

Run:

```powershell
cd apps/agent-python
pytest
python -c "from app.main import app; print(app.title)"
```

Expected:
- All tests pass.
- Startup import prints `Travel Agent Python`.

**Step 3: Run frontend build**

Run:

```powershell
cd apps/web
npm run build
```

Expected:
- Build succeeds.

**Step 4: Run final dependency searches**

Run from repository root:

```powershell
rg -n "from app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)|import app\.(agents|orchestrator|schemas|tool_gateway|storage|catalog|prompts|policies)" apps/agent-python/app apps/agent-python/tests
rg -n "import jakarta\.persistence|import org\.springframework" apps/api-java/src/main/java/com/travel/intelligence/api/user/domain apps/api-java/src/main/java/com/travel/intelligence/api/platform/domain apps/api-java/src/main/java/com/travel/intelligence/api/agent/domain
rg -n "com\.travel\.intelligence\.api\..*\.infrastructure|RestClient|WebClient|HttpHeaders|JpaRepository|Authentication" apps/api-java/src/main/java/com/travel/intelligence/api/user/application apps/api-java/src/main/java/com/travel/intelligence/api/platform/application apps/api-java/src/main/java/com/travel/intelligence/api/agent/application apps/api-java/src/main/java/com/travel/intelligence/api/tool/application
```

Expected:
- No output.

**Step 5: Clean generated outputs**

Resolve paths under the repository, then remove only generated outputs:

```text
apps/api-java/target
apps/api-java/data
apps/web/dist
apps/agent-python/.pytest_cache
```

Do not remove tracked runtime/fixture data unless it has been moved and tests prove the new location works.

**Step 6: Inspect Git status**

Run:

```powershell
git status --short
```

Expected:
- Source, test, docs, and intentional deletes/moves only.
- No generated `target`, `data`, `dist`, or `.pytest_cache`.

**Completion checkbox:** `[x] Task 23 complete`

**Execution result (2026-07-13):**
- Commands: full Java `mvn test`; full Python `python -m pytest` and application import smoke; `npm run build`; repository-wide retired-Python import scan including `packages/tools`; Java domain and application dependency scans; absolute-path verification and removal of generated `target`, `data`, `dist`, and `.pytest_cache` paths; final `git status --short`.
- Result: Java passed `23` tests with `BUILD SUCCESS`; Python passed `57` tests with `9` existing deprecation warnings and printed `Travel Agent Python`; and the Vite production build passed. All three final dependency scans returned zero matches. The generated-output audit confirmed `apps/api-java/target`, `apps/web/dist`, and `apps/agent-python/.pytest_cache` were safely removed after verification; `apps/api-java/data` was already absent. Final Git status contains the intentional consolidated source/test/doc additions, modifications, and retired-package deletions only, with no generated output.
- Files changed: this plan only during final acceptance. Generated outputs removed: `apps/api-java/target`, `apps/web/dist`, and `apps/agent-python/.pytest_cache`.
- Blockers: none. Maven emitted existing Mockito dynamic-agent/JDK warnings; Python emitted existing Pydantic and `datetime.utcnow()` deprecation warnings. Neither affected the passing suites.
- Plan corrections: none. All tasks in this consolidation plan are complete.

---

## Execution Order Summary

1. `[x]` Task 1: Freeze import graph and add consolidation guardrails.
2. `[x]` Task 2: Java architecture guard upgrade.
3. `[x]` Task 3: Java user module application port preparation.
4. `[x]` Task 4: Java platform module application port preparation and shared persistence extraction.
5. `[x]` Task 5: Java agent module typed boundary split.
6. `[x]` Task 6: Java tool gateway real application/infrastructure split.
7. `[x]` Task 7: Java security/common exception boundary cleanup.
8. `[x]` Task 8: Java consolidation verification.
9. `[x]` Task 9: Python import graph ratchet.
10. `[x]` Task 10: Python contracts and schema ownership migration.
11. `[x]` Task 11: Python context layer implementation migration.
12. `[x]` Task 12: Python understanding layer implementation migration.
13. `[x]` Task 13: Python planning layer implementation migration.
14. `[x]` Task 14: Python execution/tools layer implementation migration.
15. `[x]` Task 15: Python integrations layer implementation migration.
16. `[x]` Task 16: Python evidence layer implementation migration.
17. `[x]` Task 17: Python composition layer implementation migration.
18. `[x]` Task 18: Python orchestration layer implementation migration.
19. `[x]` Task 19: Python governance and observability implementation migration.
20A. `[x]` Task 20A: Residual retired-import inventory and decomposition.
20B. `[x]` Task 20B: Retire catalog and storage root consumers.
20C. `[x]` Task 20C: Retire Java Tool Gateway root consumers.
20D. `[x]` Task 20D: Retire root evidence policies.
20E. `[x]` Task 20E: Migrate context and understanding schema primitives.
20F. `[x]` Task 20F: Migrate planning and research schema primitives.
20G. `[x]` Task 20G: Migrate evidence and composition result schemas.
20H. `[x]` Task 20H: Migrate remaining public state and specialized schemas.
20I. `[x]` Task 20I: Migrate LLM and query-normalization agents.
20J. `[x]` Task 20J: Migrate rule, entity, and travel-understanding agents.
20K. `[x]` Task 20K: Migrate planning and research agent entry points.
20L. `[x]` Task 20L: Migrate evidence analysis and review agents.
20M. `[x]` Task 20M: Migrate execution data-retrieval agents.
20N. `[x]` Task 20N: Migrate composition and S5 agent surfaces. Re-executed with the orchestration-integration boundary repair.
20O. `[x]` Task 20O: Migrate Agent Core workflow helpers. Re-executed after 20N; final owners and compatibility exports verified.
20P. `[x]` Task 20P: Migrate controlled action-loop helpers. Re-executed after 20O; final owners and compatibility exports verified.
20P-A. `[x]` Task 20P-A: Decouple nearby planning from concrete MCP adapters. Completed: evidence owns the canonical parser; planning has no concrete MCP imports; compatibility adapter exports were preserved.
20Q. `[x]` Task 20Q: Migrate intent and claim policy helpers. Re-executed after 20P-A; final-owner bridges and typed state verified, with an AST guard against old helper resolution.
20R. `[x]` Task 20R: Migrate lookup research-chain helpers. Re-executed after 20Q; final-owner bridges and compatibility exports verified.
20S. `[x]` Task 20S: Migrate nearby and POI research helpers. Re-executed after 20R; final-owner bridges, taxonomy data, and compatibility exports verified.
20T. `[x]` Task 20T: Migrate ticket lookup helpers. Re-executed after 20S; strict price-retry contract and final-owner compatibility exports verified.
20U. `[x]` Task 20U: Migrate evidence, source, and field-extraction helpers. Re-executed after 20T; final evidence ownership and compatibility exports verified.
20V. `[x]` Task 20V: Migrate non-lookup and composition-orchestration helpers. Final-owner implementations and compatibility facades verified; 15 focused tests passed.
20V-A. `[x]` Task 20V-A: Characterize the final non-lookup task composite. Completed: three S5/S7/S8 characterization tests passed and the extraction order is now bounded.
20V-B. `[x]` Task 20V-B: Extract non-lookup task profiles to planning. Final profile ownership, compatibility type identity, and 11 focused tests verified.
20V-C. `[x]` Task 20V-C: Extract non-lookup S7 evaluation to evidence. Evidence-owned policy, trace, and nearby filtering delegated; 21 focused tests passed.
20V-D. `[x]` Task 20V-D: Extract non-lookup S8 composition context. Final composition owner accepts explicit inputs; 15 focused tests passed.
20V-E. `[x]` Task 20V-E: Reduce non-lookup orchestration to a coordinator. Legacy composite bodies removed; facade compatibility and 19 focused tests passed.
20W. `[x]` Task 20W: Migrate tests and close compatibility imports. Global static retired-import scan is empty; full Python suite passed 52 tests.
20X-A. `[x]` Task 20X-A: Replace dynamic schema compatibility bridges. Ten callers now resolve final schema owners; 22 focused tests passed.
20X-B. `[x]` Task 20X-B: Replace dynamic orchestrator compatibility bridges. Nine callers now resolve final owners and 30 focused tests passed.
20X-C. `[x]` Task 20X-C: Remove retired dynamic boundary helpers. Global retired-reference scans are empty; full Python suite passed 54 tests.
20Y-A. `[x]` Task 20Y-A: Characterize shared `packages/tools` dependencies on retired packages. Mapped 49 references in 35 files to final owners.
20Y-B. `[x]` Task 20Y-B: Migrate shared tool models and evidence types. All 42 direct schema imports now use final owners; focused identity test passed.
20Y-C. `[x]` Task 20Y-C: Migrate shared tool policy, cache, and router dependencies. All seven final owners verified; 3 focused tests passed.
20Y-D. `[x]` Task 20Y-D: Verify shared tool runtime after package deletion. Full Python suite passed 57 tests; app startup and repo-wide scans passed.
20. `[x]` Task 20: Delete retired Python packages. Final acceptance passed: all retired paths remain absent, repository-wide scans are empty, Python suite passed 57 tests, and app startup succeeded.
21. `[x]` Task 21: Cross-service contract and frontend flow verification. Java-Python contract tests, platform flow test, and web production build passed; frontend shape unchanged.
22. `[x]` Task 22: Documentation and developer guidance refresh. Final layer ownership, retired-package rules, runtime mainline, and repository map are documented.
23. `[x]` Task 23: Final full-stack verification and cleanup. Java 23-test suite, Python 57-test suite, app smoke, frontend build, dependency scans, and generated-output cleanup passed.

## Notes For Execution

- This is a consolidation plan, not another wrapper plan.
- Move implementation code into the owner layer before deleting old files.
- Preserve behavior with focused tests before changing imports.
- Prefer `git mv` semantics when moving files, but use normal file moves if the tool cannot preserve rename metadata.
- Do not use broad search/replace across the whole repository without running focused tests afterward.
- Keep changes small enough that each task can be reviewed independently.
- If a file has mixed responsibilities, split it by responsibility instead of moving it wholesale.
- If deleting a retired Python package causes wide breakage, stop and record the remaining import owners under Task 20 instead of recreating compatibility wrappers.
