# Evidence-first Travel Agent Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** 将当前“大而散、运行链与测试链脱节”的旅行 Agent 收敛为一个只支持景点事实问答、适合度建议、景点比较和多轮澄清的可审计系统，并用最小动态 RAG 与离线 Eval 证明其可靠性。

**Architecture:** Python 端采用单一显式状态运行时，每个状态都通过 `StateContext -> StateResult` 契约运行，由静态转移表约束合法路径并把失败、恢复和提交写入审计存储。景点知识位于现有 `app.evidence` 能力域下的 `knowledge` 子包，以 SQLite + FTS5 管理文档版本、事实块和检索日志。回答先产出逐条 `AnswerClaim`，再由 Citation Guard 完成 claim 到 evidence/chunk/version/URL 的闭环验证。Java 只负责平台数据、会话和代理边界；Web 只展示稳定响应契约。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic v2、stdlib SQLite/FTS5、pytest/pytest-asyncio；Java 21、Spring Boot 3.4、JUnit/MockMvc；Vite、浏览器原生 JavaScript、Node 内置测试运行器；GitHub Actions。

---

## 实施原则

- 所有运行时修改测试先行；先得到预期失败，再写最小实现。
- 不依赖真实 LLM、搜索或爬虫完成默认 CI；真实模型评测作为手动 profile。
- 不引入向量数据库、消息队列、分布式恢复或新前端框架。
- 每个任务形成独立提交；测试不通过不进入下一任务。
- 删除能力前先用 characterization test 固定保留行为，再用 import/scope gate 防止旧能力回流。
- RAG 实现在 `apps/agent-python/app/evidence/knowledge/`。这是对设计文档中 `app.knowledge` 示例路径的仓库规范适配，不改变数据模型或行为。

## Task 1：建立基线与保留能力契约

**Files:**

- Create: `apps/agent-python/evals/__init__.py`
- Create: `apps/agent-python/evals/baseline.py`
- Create: `apps/agent-python/evals/reports/baseline-current.json`
- Create: `apps/agent-python/tests/characterization/test_current_api_contract.py`
- Create: `apps/agent-python/tests/characterization/test_supported_scope.py`
- Modify: `apps/agent-python/tests/test_agent_capability_boundaries.py`
- Modify: `.gitignore`

**Step 1: 写失败的 API characterization tests**

用一个注入 fake state machine 的 `AgentRunService` 测试当前稳定字段，明确 `session_id` 必须原样传入状态机，且 `debug=false` 不写调试文件：

```python
@pytest.mark.asyncio
async def test_query_propagates_session_and_keeps_public_contract():
    machine = RecordingStateMachine(response=legacy_response())
    writer = Mock()
    service = AgentRunService(machine, writer, logger=Mock())

    response = await service.query(
        AgentQueryRequest(query="故宫需要预约吗", session_id="s-1", debug=False)
    )

    assert machine.calls[0].session_id == "s-1"
    assert response.model_dump().keys() >= {
        "answer", "session_id", "query_id", "evidence_summary",
        "limitations", "confidence", "citation_check_result",
    }
    writer.assert_not_called()
```

**Step 2: 运行测试并确认失败**

Run:

```powershell
cd apps/agent-python
pytest tests/characterization/test_current_api_contract.py -q
```

Expected: FAIL，指出 `AgentStateMachine.run` 没有 `session_id/debug/trace_id` 契约，且 debug writer 被无条件调用。

**Step 3: 写支持范围测试**

`test_supported_scope.py` 固定四类可接受任务：`fact_query`、`suitability`、`comparison`、`clarification`；同时列出禁止的运行能力标记：`itinerary`、`nearby`、`crowd_estimation`、`review_crawler`、`ticket_crawler`。此时只记录现状，不删除代码。

**Step 4: 保存当前测试与规模基线**

`evals/baseline.py` 收集：Python/Java/Web 测试结果、Python 生产代码文件数与行数、测试文件数与行数、当前受支持能力。生成的临时文件写到 ignored 的 `evals/reports/generated/`；仅提交人工确认后的 `baseline-current.json`。

Run:

```powershell
python evals/baseline.py --output evals/reports/baseline-current.json
pytest -q
cd ../api-java
mvn test
cd ../web
npm run build
```

Expected: Python 现有 57 个测试、Java 现有 23 个测试和 Web build 通过；baseline JSON 带命令退出码与代码规模。

**Step 5: Commit**

```powershell
git add .gitignore apps/agent-python/evals apps/agent-python/tests/characterization apps/agent-python/tests/test_agent_capability_boundaries.py
git commit -m "test: capture agent consolidation baseline"
```

## Task 2：定义状态运行时、错误分类和静态转移表

**Files:**

- Create: `apps/agent-python/app/orchestration/state_contracts.py`
- Create: `apps/agent-python/app/orchestration/transition_table.py`
- Create: `apps/agent-python/app/orchestration/state_runtime.py`
- Create: `apps/agent-python/app/orchestration/state_audit.py`
- Create: `apps/agent-python/tests/test_state_runtime.py`
- Create: `apps/agent-python/tests/test_state_audit.py`
- Modify: `apps/agent-python/app/governance/failure_reason.py`
- Modify: `apps/agent-python/app/governance/retry_policy.py`
- Modify: `apps/agent-python/app/governance/tool_budget.py`

**Step 1: 写状态契约与非法转移测试**

```python
def test_runtime_rejects_illegal_transition_and_audits_failure():
    runtime = StateRuntime(
        handlers={AgentState.INGRESS: HandlerReturning(AgentState.COMPOSE)},
        audit=InMemoryStateAuditStore(),
    )

    result = asyncio.run(runtime.run(context_for("故宫开放时间")))

    assert result.terminal_state is AgentState.FAILED
    assert result.failure.code == "illegal_transition"
    assert result.audit_events[-1].event_type == "phase_failed"
```

再覆盖：单状态超时、可恢复失败只重试一次、最大步数、终止态不得继续运行、每次成功转移必须有 `transition_committed`。

**Step 2: 运行并确认失败**

Run: `cd apps/agent-python; pytest tests/test_state_runtime.py tests/test_state_audit.py -q`

Expected: FAIL because modules do not exist.

**Step 3: 实现最小状态协议**

`state_contracts.py` 定义：

```python
class AgentState(StrEnum):
    INGRESS = "ingress"
    CONTEXT = "context"
    UNDERSTAND = "understand"
    ROUTE = "route"
    CLARIFICATION = "clarification"
    FACT_QUERY = "fact_query"
    SUITABILITY = "suitability"
    COMPARISON = "comparison"
    RAG_RETRIEVE = "rag_retrieve"
    LIVE_GAP_FILL = "live_gap_fill"
    EVIDENCE_EVALUATE = "evidence_evaluate"
    COMPOSE = "compose"
    CITATION_GUARD = "citation_guard"
    LIMITED_ANSWER = "limited_answer"
    SAFE_FAILURE = "safe_failure"
    DELIVER = "deliver"
    FAILED = "failed"

class FailureClass(StrEnum):
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    EMPTY_RESULT = "empty_result"
    PARSE_ERROR = "parse_error"
    POLICY_DENIED = "policy_denied"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    ILLEGAL_TRANSITION = "illegal_transition"
    UNSUPPORTED_CLAIM = "unsupported_claim"

class StateResult(BaseModel):
    status: Literal["succeeded", "failed", "recovered"]
    next_state: AgentState
    output: dict = Field(default_factory=dict)
    failure: StateFailure | None = None
    recovery: RecoveryRecord | None = None
```

`StateContext` 只保存可审计业务状态、预算、版本号和 artifact references，不保存 chain-of-thought。

**Step 4: 实现静态转移表与运行器**

允许的主路径严格来自批准设计。`StateRuntime` 在调用 handler 前后写入 `phase_started`、`phase_succeeded/failed/recovered`、`transition_committed`，并用 `asyncio.timeout` 实现 deadline；预算耗尽进入 `LIMITED_ANSWER` 或 `SAFE_FAILURE`。

**Step 5: 运行测试**

Run: `pytest tests/test_state_runtime.py tests/test_state_audit.py -q`

Expected: PASS.

**Step 6: Commit**

```powershell
git add apps/agent-python/app/orchestration apps/agent-python/app/governance apps/agent-python/tests/test_state_runtime.py apps/agent-python/tests/test_state_audit.py
git commit -m "feat: add auditable state runtime"
```

## Task 3：实现最小动态景点知识库

**Files:**

- Create: `apps/agent-python/app/evidence/knowledge/__init__.py`
- Create: `apps/agent-python/app/evidence/knowledge/models.py`
- Create: `apps/agent-python/app/evidence/knowledge/schema.sql`
- Create: `apps/agent-python/app/evidence/knowledge/repository.py`
- Create: `apps/agent-python/app/evidence/knowledge/service.py`
- Create: `apps/agent-python/app/evidence/knowledge/cli.py`
- Create: `apps/agent-python/tests/knowledge/test_repository.py`
- Create: `apps/agent-python/tests/knowledge/test_lifecycle.py`
- Modify: `apps/agent-python/app/config.py`
- Modify: `apps/agent-python/.env.example`

**Step 1: 写版本生命周期测试**

覆盖以下不变量：

```python
def test_publish_supersedes_previous_active_version(repo):
    first = repo.ingest(document(url=URL, content="09:00-17:00"))
    repo.publish(first.version_id)
    second = repo.ingest(document(url=URL, content="08:30-17:00"))
    repo.publish(second.version_id)

    assert repo.get_version(first.version_id).status == VersionStatus.SUPERSEDED
    assert repo.get_version(second.version_id).status == VersionStatus.ACTIVE
    assert repo.active_versions(attraction_id=ATTRACTION_ID) == [second]

def test_same_hash_is_idempotent(repo): ...
def test_expired_version_is_not_active(repo): ...
def test_untrusted_source_stays_pending(repo): ...
```

**Step 2: 运行并确认失败**

Run: `cd apps/agent-python; pytest tests/knowledge/test_repository.py tests/knowledge/test_lifecycle.py -q`

Expected: FAIL because knowledge package does not exist.

**Step 3: 实现数据模型与 SQLite schema**

表：`attraction`、`source_document`、`document_version`、`fact_chunk`、`fact_chunk_fts`、`retrieval_log`。状态仅允许 `pending/active/superseded/expired/rejected`。事实类型仅允许：`opening_hours`、`ticket_price`、`reservation`、`transport`、`accessibility`、`visitor_notice`、`general_description`。

必须建立：

- `(source_document_id, content_hash)` 唯一索引。
- 每个 source document 最多一个 active version 的 partial unique index。
- `fact_chunk_fts` 与 `fact_chunk` 的同步触发器。
- active/status、attraction/fact_type 和 expiry 查询索引。

**Step 4: 实现 repository/service/CLI**

CLI：

```powershell
python -m app.evidence.knowledge.cli seed --db data/knowledge.sqlite3 --fixture evals/fixtures/knowledge.json
python -m app.evidence.knowledge.cli refresh --db data/knowledge.sqlite3 --source-id source-forbidden-city
python -m app.evidence.knowledge.cli publish --db data/knowledge.sqlite3 --version-id ver-002
python -m app.evidence.knowledge.cli inspect --db data/knowledge.sqlite3 --attraction forbidden-city
```

`refresh` 只创建/返回版本，不让 live query 自动发布；官方/结构化 fixture 可通过 service 的 deterministic validation 后自动发布。

**Step 5: 运行测试和 CLI smoke test**

Run:

```powershell
pytest tests/knowledge/test_repository.py tests/knowledge/test_lifecycle.py -q
python -m app.evidence.knowledge.cli --help
```

Expected: PASS，CLI exit 0。

**Step 6: Commit**

```powershell
git add apps/agent-python/app/evidence/knowledge apps/agent-python/app/config.py apps/agent-python/.env.example apps/agent-python/tests/knowledge
git commit -m "feat: add versioned attraction knowledge store"
```

## Task 4：实现 FTS5 检索、provenance 和 RAG Eval

**Files:**

- Create: `apps/agent-python/app/evidence/knowledge/retriever.py`
- Create: `apps/agent-python/evals/fixtures/knowledge.json`
- Create: `apps/agent-python/evals/datasets/retrieval.jsonl`
- Create: `apps/agent-python/evals/datasets/versioning.jsonl`
- Create: `apps/agent-python/evals/graders/retrieval.py`
- Create: `apps/agent-python/evals/runner.py`
- Create: `apps/agent-python/tests/knowledge/test_retriever.py`
- Create: `apps/agent-python/tests/evals/test_retrieval_grader.py`
- Modify: `apps/agent-python/app/evidence/evidence_model.py`
- Modify: `contracts/schemas/evidence.schema.json`

**Step 1: 写检索与 provenance 失败测试**

```python
def test_retriever_returns_only_active_chunks_with_full_provenance(seed_store):
    report = retriever.search("故宫需要预约吗", attraction_ids=["forbidden-city"], top_k=3)

    assert report.hits
    assert all(hit.version_status == "active" for hit in report.hits)
    assert all(hit.evidence.provenance.chunk_id for hit in report.hits)
    assert all(hit.evidence.provenance.document_version_id for hit in report.hits)
    assert all(hit.evidence.source_url.startswith("https://") for hit in report.hits)
```

同时覆盖：expired leakage 为零、同名景点 entity filter、fact_type filter、Top-K 稳定排序、零结果返回完整 `RetrievalReport`。

**Step 2: 运行并确认失败**

Run: `pytest tests/knowledge/test_retriever.py tests/evals/test_retrieval_grader.py -q`

Expected: FAIL.

**Step 3: 实现检索管线**

顺序固定为：entity resolution result → attraction/fact filters → FTS5 BM25 Top-K → source authority/freshness/claim match rer排 → `Evidence` 转换 → coverage hints → retrieval log。

评分公式固定并写入测试：

```python
final_score = (
    0.55 * normalized_bm25
    + 0.20 * source_authority
    + 0.15 * freshness_score
    + 0.10 * fact_type_match
)
```

`EvidenceProvenance` 增加 `source_id/document_version_id/chunk_id/content_hash/locator/valid_from/valid_to/retrieval_score`。

**Step 4: 建立最小 fixture 和 graders**

fixture 规模固定：8 个景点、约 40 个 active chunks、12 个 stale/superseded chunks、8 个 conflicting/pending chunks。不得复制大篇网页正文；每条 chunk 是为评测编写的短事实，保留可验证 source URL。

`runner.py` 支持：

```powershell
python -m evals.runner --suite retrieval --offline --report evals/reports/generated/retrieval.json
python -m evals.runner --suite versioning --offline --report evals/reports/generated/versioning.json
```

输出 `recall_at_3`、`mrr`、`active_version_accuracy`、`expired_leakage_rate`、`provenance_completeness`。

**Step 5: 运行测试和 Eval**

Expected gates：Recall@3 ≥ 0.90、active version accuracy = 1.0、expired leakage = 0、provenance completeness = 1.0。

**Step 6: Commit**

```powershell
git add apps/agent-python/app/evidence apps/agent-python/evals apps/agent-python/tests/knowledge apps/agent-python/tests/evals contracts/schemas/evidence.schema.json
git commit -m "feat: add attraction retrieval eval loop"
```

## Task 5：实现 Ingress、Context、Understand、Route 状态

**Files:**

- Create: `apps/agent-python/app/orchestration/states/ingress.py`
- Create: `apps/agent-python/app/orchestration/states/context_loading.py`
- Create: `apps/agent-python/app/orchestration/states/routing.py`
- Create: `apps/agent-python/tests/states/test_ingress_context.py`
- Create: `apps/agent-python/tests/states/test_understand_route.py`
- Create: `apps/agent-python/evals/datasets/state_routing.jsonl`
- Modify: `apps/agent-python/app/orchestration/states/llm_understanding.py`
- Modify: `apps/agent-python/app/understanding/rule_based_understanding.py`
- Modify: `apps/agent-python/app/context/session_context.py`
- Modify: `apps/agent-python/app/composition/response_contract.py`

**Step 1: 写逐状态退出门测试**

- Ingress：空 query → `SAFE_FAILURE`；相同 idempotency key → 返回同一 run。
- Context：缺失 session 生成一个；存在 session 则加载历史；存储失败可恢复为空上下文但必须审计。
- Understand：结构化解析失败只 repair 一次；仍失败则规则 fallback；实体仍不足进入 clarification。
- Route：只产生四类 task；comparison 必须有两个独立 `subtask_id`；其他任务进入 clarification。

```python
@pytest.mark.asyncio
async def test_understand_repairs_once_then_uses_rule_fallback():
    handler = UnderstandHandler(llm=MalformedTwice(), fallback=RuleUnderstanding())
    result = await handler.run(context_for("故宫和颐和园哪个更适合老人"))
    assert result.status == "recovered"
    assert result.output["task_type"] == "comparison"
    assert result.recovery.strategy == "rule_fallback"
    assert handler.llm.calls == 2
```

**Step 2: 运行并确认失败**

Run: `pytest tests/states/test_ingress_context.py tests/states/test_understand_route.py -q`

**Step 3: 实现 handler 适配层**

复用现有 `LLMUnderstandingState` 与 rule-based parsing，但不允许其自行跳转或吞异常。每个 handler 只返回 `StateResult`；是否重试、转向或终止由 runtime/policy 决定。

**Step 4: 增加 routing eval**

8 条固定 case，覆盖事实、适合度、对比、多轮指代、缺实体、已裁剪请求。已裁剪请求必须被路由到 clarification 或 safe failure，不得偷偷进入旧链。

**Step 5: 运行状态测试和 routing eval**

Expected: path accuracy ≥ 0.95、illegal transitions = 0、clarification precision = 1.0 on fixture。

**Step 6: Commit**

```powershell
git add apps/agent-python/app/orchestration/states apps/agent-python/app/understanding apps/agent-python/app/context apps/agent-python/app/composition/response_contract.py apps/agent-python/tests/states apps/agent-python/evals/datasets/state_routing.jsonl
git commit -m "feat: add guarded ingress and routing states"
```

## Task 6：实现 RAG Retrieve、Evidence Evaluate 和受控 Live Gap Fill

**Files:**

- Create: `apps/agent-python/app/orchestration/states/rag_retrieval.py`
- Create: `apps/agent-python/app/orchestration/states/evidence_evaluation.py`
- Create: `apps/agent-python/app/orchestration/states/live_gap_fill.py`
- Create: `apps/agent-python/app/evidence/claim_decision.py`
- Create: `apps/agent-python/tests/states/test_rag_retrieval.py`
- Create: `apps/agent-python/tests/states/test_evidence_evaluation.py`
- Create: `apps/agent-python/tests/states/test_live_gap_fill.py`
- Create: `apps/agent-python/tests/fakes/failing_tools.py`
- Create: `apps/agent-python/evals/datasets/evidence_conflict.jsonl`
- Create: `apps/agent-python/evals/datasets/failure_recovery.jsonl`
- Modify: `apps/agent-python/app/evidence/conflict_resolver.py`
- Modify: `apps/agent-python/app/evidence/coverage_checker.py`
- Modify: `apps/agent-python/app/execution/retry_policy.py`
- Modify: `apps/agent-python/app/execution/timeout_policy.py`

**Step 1: 写 retrieval/evaluation 退出门测试**

`RAG_RETRIEVE` 无论命中与否都输出 `RetrievalReport`。`EVIDENCE_EVALUATE` 必须输出 `ClaimDecision[] + CoverageReport`；冲突证据不被静默删除；只允许一个 gap round。

比较任务为每个景点独立保存 `subtask_id`、retrieval report 和 coverage，只允许共同 claim dimension 进入比较回答。

**Step 2: 写故障注入测试**

fakes 提供：`timeout_once`、`always_empty`、`rate_limit_then_success`、`malformed_payload`、`stale_only`、`conflicting_sources`。断言每类失败的 `FailureClass`、attempt 数、recovery strategy 和最终状态。

**Step 3: 运行并确认失败**

Run:

```powershell
pytest tests/states/test_rag_retrieval.py tests/states/test_evidence_evaluation.py tests/states/test_live_gap_fill.py -q
```

**Step 4: 实现三个状态**

- RAG 首查；DB unavailable 进入一次 live gap，不直接崩溃。
- Evidence Evaluate 丢弃结构非法项、保留并标注 conflict、计算 claim coverage。
- Live gap 最多一次外部调用；timeout/429 最多 retry once；provider fallback 也受同一总预算约束。
- live 结果只作为本次 run 的 transient evidence；可选写 pending version，绝不自动污染 active corpus。

**Step 5: 运行测试与 failure eval**

Expected: 最大外部调用次数满足预算；重试次数 ≤ 1；所有恢复都有审计；无法支持硬事实时 abstain。

**Step 6: Commit**

```powershell
git add apps/agent-python/app/orchestration/states apps/agent-python/app/evidence apps/agent-python/app/execution apps/agent-python/tests/states apps/agent-python/tests/fakes apps/agent-python/evals/datasets
git commit -m "feat: add bounded evidence recovery states"
```

## Task 7：实现 AnswerClaim、Compose、Citation Guard 和终止态

**Files:**

- Create: `apps/agent-python/app/composition/answer_claim.py`
- Create: `apps/agent-python/app/orchestration/states/citation_guard.py`
- Create: `apps/agent-python/app/orchestration/states/delivery.py`
- Create: `apps/agent-python/tests/states/test_composition.py`
- Create: `apps/agent-python/tests/states/test_citation_guard.py`
- Create: `apps/agent-python/evals/datasets/citation.jsonl`
- Create: `apps/agent-python/evals/graders/citation.py`
- Modify: `apps/agent-python/app/composition/final_answer_draft.py`
- Modify: `apps/agent-python/app/composition/answer_composer.py`
- Modify: `apps/agent-python/app/orchestration/states/answer_composition.py`
- Modify: `apps/agent-python/app/evidence/citation_checker.py`
- Modify: `apps/agent-python/app/contracts/response.py`
- Modify: `contracts/schemas/travel_query_response.schema.json`

**Step 1: 写 claim 级引用测试**

```python
def test_unsupported_hard_fact_is_removed_before_delivery():
    draft = FinalAnswerDraft(
        answer_claims=[
            AnswerClaim(text="故宫每天 24 小时开放", claim_type="opening_hours", evidence_ids=[]),
            AnswerClaim(text="建议提前核对官方公告", claim_type="advice", evidence_ids=[]),
        ]
    )
    result = CitationGuard().run(context_with(draft=draft))
    assert "24 小时" not in result.output["answer"]
    assert result.next_state is AgentState.LIMITED_ANSWER
    assert result.output["citation_decisions"][0]["status"] == "unsupported_removed"
```

覆盖：错误 evidence ID、证据版本非 active、URL 缺失、conflict 未披露、软建议不要求硬引用、所有硬事实都被移除时进入 safe failure。

**Step 2: 运行并确认失败**

Run: `pytest tests/states/test_composition.py tests/states/test_citation_guard.py -q`

**Step 3: 实现结构化 AnswerClaim**

每条 claim 至少包含：`claim_id/text/claim_type/hard_fact/evidence_ids/attraction_id/subtask_id`。Compose 若 LLM 输出不可解析只 repair 一次；仍失败使用 evidence template 生成受限回答。

**Step 4: 重写 CitationChecker 边界**

禁止再以空 `fact_sheets/review_results` 调用全局文本匹配。CitationChecker 接收 `AnswerClaim[]` 与 evidence index，输出逐 claim `CitationDecision` 和总 `CitationReport`。对 hard fact 采用 fail closed。

**Step 5: 运行 citation eval**

输出 citation precision/recall、unsupported hard facts、claim accuracy、conflict disclosure、abstention precision。

Expected: citation precision ≥ .95、unsupported hard facts = 0、abstention precision ≥ .90。

**Step 6: Commit**

```powershell
git add apps/agent-python/app/composition apps/agent-python/app/orchestration/states apps/agent-python/app/evidence/citation_checker.py apps/agent-python/app/contracts/response.py apps/agent-python/tests/states apps/agent-python/evals contracts/schemas/travel_query_response.schema.json
git commit -m "feat: enforce claim level citation guard"
```

## Task 8：收敛 Agent Core Store 并实现 inspect/replay

**Files:**

- Replace: `apps/agent-python/app/orchestration/agent_core_models.py`
- Replace: `apps/agent-python/app/orchestration/agent_core_store.py`
- Create: `apps/agent-python/app/orchestration/run_inspector.py`
- Create: `apps/agent-python/app/orchestration/replay.py`
- Create: `apps/agent-python/app/orchestration/run_cli.py`
- Create: `apps/agent-python/tests/test_agent_core_store.py`
- Create: `apps/agent-python/tests/test_replay.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_control_tools.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_job_reconciler.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_pipeline_gate.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_research_plan.py`

**Step 1: 写 store schema 与 replay 测试**

store 只暴露：`run`、`phase_event`、`execution_attempt`、`evidence_record`、`answer_claim`、`citation_decision`、`run_metric`。测试必须证明 query-id inspect 返回完整时间线、重放不调用理解/检索/tool、从 `EVIDENCE_EVALUATE` artifact 开始得到相同 citation decisions。

**Step 2: 运行并确认失败**

Run: `pytest tests/test_agent_core_store.py tests/test_replay.py -q`

**Step 3: 实现收敛后的 SQLite store 与 CLI**

```powershell
python -m app.orchestration.run_cli inspect --query-id q-123 --db data/agent_runs.sqlite3
python -m app.orchestration.run_cli replay --query-id q-123 --from-state evidence_evaluate --db data/agent_runs.sqlite3
```

replay 读取已持久化 evidence/coverage artifacts，只重跑 evaluate → compose → citation → deliver；返回新 run_id 并记录 `replay_of_run_id`。

**Step 4: 删除旧 job/control/research-plan 模型**

先用 `rg` 确认引用全部迁移，再删除四个文件及其测试断言。不得保留 silent `try/except Exception: return` 的审计写入。

**Step 5: 运行测试**

Expected: replay consistency = 1.0；任何持久化失败都产生 terminal failure 或显式 recovery event。

**Step 6: Commit**

```powershell
git add -A apps/agent-python/app/orchestration apps/agent-python/tests/test_agent_core_store.py apps/agent-python/tests/test_replay.py
git commit -m "refactor: reduce run store and add replay"
```

## Task 9：把 TravelAgentStateMachine 切到唯一运行链

**Files:**

- Replace: `apps/agent-python/app/orchestration/state_machine.py`
- Modify: `apps/agent-python/app/orchestration/agent_run_service.py`
- Modify: `apps/agent-python/app/api/app_factory.py`
- Modify: `apps/agent-python/app/api/routes.py`
- Modify: `apps/agent-python/app/api/health.py`
- Modify: `apps/agent-python/app/observability/debug_session.py`
- Modify: `apps/agent-python/app/observability/logging.py`
- Modify: `apps/agent-python/app/observability/trace.py`
- Modify: `apps/agent-python/app/config.py`
- Create: `apps/agent-python/tests/integration/test_state_machine_flow.py`
- Create: `apps/agent-python/tests/integration/test_api_flow.py`
- Create: `apps/agent-python/tests/integration/test_multi_turn_flow.py`
- Create: `apps/agent-python/tests/integration/test_health_and_auth.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_supervisor.py`
- Delete: `apps/agent-python/app/orchestration/agent_core_tool_surface.py`
- Delete: `apps/agent-python/app/orchestration/claude_state_runner.py`

**Step 1: 写完整离线运行测试**

至少覆盖：

- 单景点事实：完整主链 + active RAG evidence + claim citation。
- 适合度：事实与建议分离。
- 双景点比较：两个 subtask，独立 coverage，共同比较维度。
- 多轮澄清：第二轮复用同一个 session_id。
- RAG 缺口 + tool timeout：进入 limited answer。
- debug=false：不产生 `debug_last_session.md`。
- service key 配置时：缺失/错误 key 返回 401，正确 key 通过。

**Step 2: 运行并确认失败**

Run:

```powershell
pytest tests/integration/test_state_machine_flow.py tests/integration/test_api_flow.py tests/integration/test_multi_turn_flow.py tests/integration/test_health_and_auth.py -q
```

**Step 3: 替换 state_machine.py**

新文件只负责依赖装配与 `runtime.run`，不保留 `_dispatch_by_answer_mode`、`_run_itinerary`、`_run_crowd_inquiry` 等第二套链。签名固定：

```python
async def run(
    self,
    query: str,
    user_context: dict | None = None,
    session_id: str | None = None,
    *,
    debug: bool = False,
    trace_id: str | None = None,
) -> TravelQueryResponse:
    ...
```

**Step 4: 修复 API/observability 边界**

- `AgentRunService` 传递 session/debug/trace。
- debug writer 只在 payload.debug 与 settings.debug 同时允许时运行。
- JSON log 含 trace/session/query/state/attempt/duration/status，不记录 prompt、用户上下文、密钥和 chain-of-thought。
- `/health/live` 只表示进程；`/health/ready` 检查 knowledge DB 与必要配置；不强制真实 LLM 才允许离线路径启动。
- `X-Agent-Service-Key` 仅在设置了 key 时要求。

**Step 5: 删除 supervisor 第二链并跑全集**

Run: `pytest -q`

Expected: 所有 Python tests pass；`rg "RootAgentSupervisor|_dispatch_by_answer_mode|_run_itinerary|_run_crowd_inquiry" app tests` 无运行时命中。

**Step 6: Commit**

```powershell
git add -A apps/agent-python/app apps/agent-python/tests/integration
git commit -m "refactor: route requests through one state chain"
```

## Task 10：收紧 Java-Python 平台契约

**Files:**

- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryCommand.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/application/AgentQueryResult.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/config/AgentProperties.java`
- Modify: `apps/api-java/src/main/java/com/travel/intelligence/api/agent/infrastructure/PythonAgentClient.java`
- Modify: `apps/api-java/src/main/resources/application.yml`
- Modify: `apps/api-java/src/test/resources/application.yml`
- Create: `apps/api-java/src/test/java/com/travel/intelligence/api/agent/infrastructure/PythonAgentClientTest.java`
- Modify: `apps/api-java/src/test/java/com/travel/intelligence/api/agent/web/TravelProxyControllerTest.java`
- Modify: `apps/api-java/src/test/java/com/travel/intelligence/api/platform/web/TravelPlatformControllerTest.java`
- Modify: `contracts/schemas/travel_query_request.schema.json`
- Modify: `contracts/schemas/travel_query_response.schema.json`

**Step 1: 写失败的 Java client contract tests**

使用 `MockRestServiceServer` 验证：session_id/debug body、`X-Trace-Id`、`X-Agent-Service-Key`、Python 响应的 `orchestration_summary/answer_claims/citation_decisions/run_metrics` 映射，以及 timeout/401/5xx 的稳定错误码。

**Step 2: 运行并确认失败**

Run: `cd apps/api-java; mvn -Dtest=PythonAgentClientTest,TravelProxyControllerTest,TravelPlatformControllerTest test`

**Step 3: 实现强类型边界**

不把所有嵌套内容继续扩大为 domain model，但顶层必须成为显式 record 字段；`rawResponse` 仅作兼容诊断，不再是业务读取源。Java 为每次查询生成/传播 trace ID，平台 conversation ID 作为 session ID。

**Step 4: 运行 Java 全集**

Run: `mvn test`

Expected: PASS，Python client tests 能验证请求 header/body 与响应字段。

**Step 5: Commit**

```powershell
git add apps/api-java contracts/schemas
git commit -m "feat: harden java agent boundary"
```

## Task 11：收敛 Web 展示并增加纯函数测试

**Files:**

- Create: `apps/web/src/presentation/agent-result.js`
- Create: `apps/web/tests/agent-result.test.js`
- Modify: `apps/web/src/main.js`
- Modify: `apps/web/src/api/types.js`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/package.json`

**Step 1: 写 Node 内置测试**

不新增 Vitest/Jest。`node:test` 覆盖：

- evidence 显示 source title、URL、fact type、version/freshness。
- claim 显示 supported/limited/conflict。
- audit timeline 隐藏 input payload，只显示 phase、status、latency、recovery。
- 缺少新字段时兼容旧响应。

**Step 2: 运行并确认失败**

Run: `cd apps/web; node --test tests/agent-result.test.js`

**Step 3: 提取展示模型并修改 UI**

`main.js` 不再直接 JSON dump 全部结构；调用纯函数生成 Evidence、Citation 和 State Audit 三个可读 section。保留原 answer/confidence/limitations。

**Step 4: 运行测试与 build**

Run:

```powershell
npm test
npm run build
```

Expected: PASS。

**Step 5: Commit**

```powershell
git add apps/web
git commit -m "feat: present evidence and audit decisions"
```

## Task 12：物理裁剪超出范围的能力

**Files:**

- Delete: `apps/agent-python/app/composition/itinerary.py`
- Delete: `apps/agent-python/app/composition/nearby_guided_composition.py`
- Delete: `apps/agent-python/app/composition/prompt_templates/composer_itinerary.md`
- Delete: `apps/agent-python/app/composition/prompt_templates/composer_nearby_guided.md`
- Delete: `apps/agent-python/app/evidence/data/baidu_nearby_taxonomy.json`
- Delete: `apps/agent-python/app/evidence/nearby_category_registry.py`
- Delete: `apps/agent-python/app/evidence/nearby_enrichment_policy.py`
- Delete: `apps/agent-python/app/evidence/nearby_recommendation_policy.py`
- Delete: `apps/agent-python/app/evidence/poi_anchor_extraction.py`
- Delete: `apps/agent-python/app/evidence/review.py`
- Delete: `apps/agent-python/app/evidence/review_aspect_normalizer.py`
- Delete: `apps/agent-python/app/evidence/review_llm_extractor.py`
- Delete: `apps/agent-python/app/evidence/review_mining_agent.py`
- Delete: `apps/agent-python/app/evidence/review_persona_generator.py`
- Delete: `apps/agent-python/app/evidence/review_rule_extractor.py`
- Delete: `apps/agent-python/app/evidence/review_signal.py`
- Delete: `apps/agent-python/app/evidence/ticket_area_policy.py`
- Delete: `apps/agent-python/app/evidence/ticket_info.py`
- Delete: `apps/agent-python/app/evidence/ticket_price_audit.py`
- Delete: `apps/agent-python/app/evidence/ticket_price_extractor.py`
- Delete: `apps/agent-python/app/evidence/ticket_relevance_policy.py`
- Delete: `apps/agent-python/app/execution/nearby_enrichment_runner.py`
- Delete: `apps/agent-python/app/execution/nearby_retrieval_runner.py`
- Delete: `apps/agent-python/app/execution/ticket_lookup_attempt_tracker.py`
- Delete: `apps/agent-python/app/planning/nearby_anchor_policy.py`
- Delete: `apps/agent-python/app/planning/nearby_anchor_strategy.py`
- Delete: `apps/agent-python/app/planning/nearby_task_orchestration.py`
- Delete: `apps/agent-python/app/planning/ticket_lookup_helpers.py`
- Delete: `apps/agent-python/app/planning/ticket_lookup_policy.py`
- Delete: `apps/agent-python/app/planning/ticket_price_query_ladder.py`
- Delete: `apps/agent-python/app/planning/ticket_product_policy.py`
- Delete: `apps/agent-python/app/planning/s5_task_tool_catalogs/poi_recommendation.py`
- Delete: `apps/agent-python/app/planning/s5_task_tool_catalogs/review_first.py`
- Delete: `apps/agent-python/app/planning/s5_task_tool_catalogs/route_first.py`
- Delete: `apps/agent-python/app/planning/s5_task_tool_catalogs/ticket_price_lookup.py`
- Delete: `apps/agent-python/app/tools/review_tool.py`
- Delete: `apps/agent-python/tests/test_non_lookup_task_layers.py`
- Delete: `apps/agent-python/tests/test_poi_anchor_extraction.py`
- Delete: `apps/agent-python/tests/test_ticket_lookup_migration.py`
- Modify: `apps/agent-python/app/config.py`
- Modify: `apps/agent-python/app/composition/answer_composer.py`
- Modify: `apps/agent-python/app/planning/s5_task_tool_catalogs/resolver.py`
- Modify: `apps/agent-python/app/planning/s5_task_tool_catalogs/shared.py`
- Modify: `apps/agent-python/app/planning/s5_information_domain.py`
- Modify: `apps/agent-python/app/planning/s5_information_domain_registry.py`
- Modify: `apps/agent-python/app/tools/registry.py`
- Modify: `apps/agent-python/tests/test_supported_scope.py`

**Step 1: 将 scope gate 改为硬失败**

测试递归扫描 `app/` 的 import 与注册表，确保已裁剪模块、tool 名、intent route 和配置开关均不存在。字符串出现在 migration/design docs 不算运行时失败。

**Step 2: 运行并确认失败**

Run: `cd apps/agent-python; pytest tests/characterization/test_supported_scope.py -q`

**Step 3: 逐组删除并清理 import**

删除顺序：composition → execution/planning → evidence → tool registry/config → retired tests。`ticket_price` 作为 RAG fact type 保留，但 ticket 平台/crawler/专用查询链删除。适合度建议保留，但不依赖 review mining；只能使用 RAG 中的 accessibility/visitor_notice/general_description。

每删除一组后运行：

```powershell
python -m compileall -q app
pytest tests/test_layer_consolidation_imports.py tests/characterization/test_supported_scope.py -q
```

**Step 4: 运行全集和规模对比**

Run:

```powershell
pytest -q
python evals/baseline.py --output evals/reports/generated/after-pruning.json
```

Expected: tests pass；生产 Python 文件数与行数显著低于 Task 1 baseline；运行时无被裁剪功能引用。

**Step 5: Commit**

```powershell
git add -A apps/agent-python
git commit -m "refactor: remove unsupported travel capabilities"
```

## Task 13：项目化、CI、最终 Eval 和文档交付

**Files:**

- Create: `.github/workflows/verify.yml`
- Create: `apps/agent-python/evals/datasets/multi_turn.jsonl`
- Create: `apps/agent-python/evals/datasets/comparison.jsonl`
- Create: `apps/agent-python/evals/graders/state_path.py`
- Create: `apps/agent-python/evals/graders/evidence.py`
- Create: `apps/agent-python/evals/graders/operations.py`
- Create: `apps/agent-python/evals/reports/final-offline.json`
- Create: `apps/agent-python/evals/reports/final-offline.md`
- Create: `docs/architecture/STATE_CHAIN.md`
- Create: `docs/architecture/RAG_LIFECYCLE.md`
- Create: `docs/architecture/EVALS.md`
- Modify: `README.md`
- Modify: `RUNBOOK.md`
- Modify: `REPO_MAP.md`
- Modify: `PROJECT_MAINLINE.md`
- Modify: `AGENTS.md`

**Step 1: 完成约 50 条离线 Eval 数据**

分布：retrieval 16、versioning 8、state routing 8、evidence conflict 6、multi-turn 4、failure recovery 4、comparison 4。数据集必须带唯一 case ID、输入、fixture references、期望 path/claims/evidence IDs/failure/recovery。

**Step 2: 实现总 runner 和 gate**

Run:

```powershell
cd apps/agent-python
python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/final-offline.json
```

硬门槛：

- Recall@3 ≥ .90；MRR 被记录。
- active_version_accuracy = 1.0；expired_leakage = 0。
- state_path_accuracy ≥ .95；illegal_transition_count = 0；max_step_violation = 0。
- citation_precision ≥ .95；unsupported_hard_fact_count = 0。
- abstention_precision ≥ .90；replay_consistency = 1.0。
- P50/P95、tool calls、retries、budget exhaustion 均被记录，不因机器波动设脆弱绝对 latency gate。

**Step 3: 配置 CI**

`verify.yml` 三个 job：

1. Python：安装 requirements，pytest，offline eval。
2. Java：`mvn test`。
3. Web：`npm ci`、`npm test`、`npm run build`。

CI 不读取 `.env`，不调用真实 LLM/MCP/外网。

**Step 4: 更新架构与运行文档**

文档必须给出：唯一状态图、逐状态输入/输出/失败/恢复/审计表；RAG 发布与过期流程；Eval 数据与指标定义；一条命令启动与验证；示例 inspect/replay；已明确不支持的能力。

README 首屏只突出：state chain、dynamic attraction RAG、evidence/citation guard、offline eval results。避免把 Java/Web 作为“功能堆砌”，说明它们是平台边界与可演示壳层。

**Step 5: 全栈最终验证**

Run:

```powershell
cd apps/agent-python
pytest -q
python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/final-offline.json
cd ../api-java
mvn test
cd ../web
npm test
npm run build
```

Expected: 全部通过，最终报告达到所有硬门槛。

**Step 6: 检查仓库卫生**

Run:

```powershell
git status --short
git diff --check
rg --files | rg "(__pycache__|\.pyc$|debug_last_session|/dist/|/target/|agent_runs\.sqlite3|knowledge\.sqlite3)"
```

Expected: 只有预期文档/报告被跟踪；cache、debug、build、runtime DB 不进入 Git。

**Step 7: Commit**

```powershell
git add .github README.md RUNBOOK.md REPO_MAP.md PROJECT_MAINLINE.md AGENTS.md docs/architecture apps/agent-python/evals
git commit -m "docs: ship auditable agent evaluation project"
```

## 最终验收清单

- [ ] `TravelAgentStateMachine.run` 只经过一套显式状态运行时。
- [ ] 每个状态都有输入、输出、合法转移、timeout、attempt、recovery 和 audit test。
- [ ] session_id 在 Web → Java → Python → StateContext 全链一致。
- [ ] RAG 只管理少量景点动态事实，active/superseded/expired/pending 行为可测。
- [ ] 每条硬事实存在 AnswerClaim → Evidence → Chunk → Version → URL 链。
- [ ] comparison 的每个景点独立检索、评估和审计。
- [ ] live gap fill 最多一次，失败可以归类并转向 limited/safe response。
- [ ] inspect 与 evaluate-stage replay 可用，replay consistency = 1.0。
- [ ] itinerary/nearby/crowd/review-crawler/ticket-crawler 不再存在于运行时。
- [ ] Python、Java、Web、offline eval 均在无外网/无真实 LLM 条件下通过。
- [ ] README 展示真实 final eval 数值，而不是预设目标值。

