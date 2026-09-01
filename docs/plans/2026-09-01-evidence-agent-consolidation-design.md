# Evidence-first Travel Agent 收敛改造设计

**日期：** 2026-09-01  
**状态：** 已批准  
**目标：** 停止扩展功能面，将现有项目收敛为一个可投递、可复现、可审计、可评测的 Evidence-first Travel Agent。

## 1. 项目定位

项目作为 Matinier 的补充，不再追求大而全的旅行产品能力。最终突出四项工程能力：

1. 显式、可审计的传统 Agent 状态链。
2. 少量景点事实的动态 RAG 管理。
3. Evidence 级来源、冲突、缺口与引用控制。
4. 可复现的离线 Eval、故障注入和回归报告。

最终产品名称建议使用：

> Evidence-first Travel Agent Reliability Platform

## 2. 保留与裁剪范围

### 2.1 保留能力

- Java 用户、认证、会话、查询记录和收藏。
- Web 提问、历史、Evidence、Citation 和 trace 展示。
- 自研状态链、Policy、Executor、Reducer。
- Evidence、Claim、Coverage、Conflict、Gap Filling。
- 景点事实查询。
- 景点适合度建议。
- 景点比较。
- 多轮澄清和地点指代。
- 少量已接通的官方页面、搜索、天气工具。
- Agent Core Store，收敛为运行审计和 replay 存储。

### 2.2 裁剪能力

- 行程规划。
- 实时人流。
- 附近餐饮、酒店、停车、厕所等推荐。
- 未真正接通的票务、点评、游记和附近服务 crawler/provider。
- Placeholder MCP policies。
- 不可达的旧 orchestration 分支。
- 只为迁移存在的 shim、动态 import 和重复模块。
- 作为产品能力暴露的 mock 工具；测试数据统一迁移到 eval fixtures。
- 未接入真实运行链的治理模型壳；需要的模型必须接入，否则删除。

## 3. 方案决策

采用“外科手术式收敛”：保留现有 Java/Web、Evidence 模型、工具抽象和 Agent Core Store，合并 Python 主链并裁剪不可达能力。

不采用以下方案：

- 兼容优先：仅用 feature flag 隐藏能力会保留过多复杂度。
- Python Core 重写：架构更干净，但接近重做，不符合停止深入开发的目标。

## 4. 单一状态主链

```text
INGRESS
  -> CONTEXT
  -> UNDERSTAND
  -> ROUTE
      -> CLARIFICATION
      -> FACT_QUERY
      -> SUITABILITY
      -> COMPARISON
  -> RAG_RETRIEVE
  -> EVIDENCE_EVALUATE
      -> LIVE_GAP_FILL (最多一轮)
      -> COMPOSE
  -> CITATION_GUARD
      -> LIMITED_ANSWER
      -> SAFE_FAILURE
      -> DELIVER
```

所有用户任务共用这条主链。事实查询、适合度和比较只通过 typed task context 改变检索计划和输出契约，不再维护互相分叉的完整 orchestration runtime。

## 5. 状态执行契约

每个状态实现统一接口：

```text
StateHandler.run(StateContext) -> StateResult

StateResult
  status: succeeded | recovered | limited | failed
  next_state
  state_updates
  artifacts
  failure
  transition_reason
```

每个状态声明：

```text
required_inputs
required_outputs
allowed_next_states
timeout
max_attempts
recovery_strategy
failure_exit
audit_policy
```

所有已知异常必须转换为 `StateResult`。未知进程级异常统一进入 `FAILED`，不允许吞掉异常后继续生成。

## 6. 逐状态错误处理与审计

| 状态 | 主要错误 | 恢复与转移 | 审计重点 |
| --- | --- | --- | --- |
| `INGRESS` | 空查询、非法 context、重复请求 | 校验失败进入 `SAFE_FAILURE`；重复 ID 返回已有结果 | schema 版本、请求摘要、幂等命中 |
| `CONTEXT` | session 不存在、历史损坏、跨用户 session | 丢弃损坏历史建立最小上下文；权限错误进入 `SAFE_FAILURE` | session 来源、读取版本、丢弃字段 |
| `UNDERSTAND` | LLM 超时、非法 JSON、低置信度实体或意图 | repair 一次，再用规则 fallback；仍不确定进入 `CLARIFICATION` | 模型、Prompt、解析方式、置信度、缺失槽位 |
| `ROUTE` | task 冲突、ResponseContract 不一致 | 重新编译 contract；低置信度进入 `CLARIFICATION` | 候选路由、最终路由、理由、contract hash |
| `RAG_RETRIEVE` | 景点未解析、DB 故障、零召回、内容过期 | 未解析进入 `CLARIFICATION`；DB 故障或数据缺失进入 `LIVE_GAP_FILL` | query、filter、corpus version、Top-K、score |
| `LIVE_GAP_FILL` | timeout、429、空结果、解析失败、策略拒绝 | 可恢复错误重试一次；备用来源一次；之后回到评估 | attempt、provider、failure、恢复理由、预算 |
| `EVIDENCE_EVALUATE` | 非法 Evidence、冲突、required claim 缺失 | 丢弃非法 Evidence；保留冲突双方；允许一次 Gap Fill；Evaluator 失败使用确定性 scorer | Evidence 接受/拒绝、coverage、conflict decision |
| `COMPOSE` | 超时、非法 schema、空答案、引用 ID 不存在 | repair 一次；之后使用确定性 Evidence 模板 | 输入 claim、草稿、fallback、AnswerClaim 列表 |
| `CITATION_GUARD` | claim 无 Evidence、引用错配、Evidence 失效 | 删除不支持句子；硬事实不足进入 `LIMITED_ANSWER`；无可交付内容进入 `SAFE_FAILURE` | 每个 AnswerClaim 的 citation decision |
| `DELIVER` | response schema 失败、持久化失败、重复交付 | schema 修复；使用 query ID 幂等重试 | response hash、交付状态、Java record ID |
| `CLARIFICATION` | 问题为空或重复 | 使用确定性缺失槽位模板 | 缺失槽位、问题、来源状态 |
| `LIMITED_ANSWER` | 部分事实不足 | 只输出已支持事实和明确限制 | 删除 claim、缺失项、最终置信度 |
| `SAFE_FAILURE` | 无法安全回答 | 返回稳定错误契约 | failure code、用户可见信息 |
| `FAILED` | 未分类系统异常 | 终止 run | 异常类型、最后成功状态、correlation ID |

每次状态执行固定生成：

```text
phase_started
phase_succeeded
phase_failed
phase_recovered
transition_committed
```

审计记录包含：

```text
run_id
state_name
attempt
started_at / ended_at
input_artifact_refs / output_artifact_refs
input_digest / output_digest
status
failure_code
recovery_action
from_state / to_state
transition_reason
model_version
prompt_version
corpus_version
tool_config_hash
```

不保存模型原始思维链，只保存结构化决策、理由摘要、输入输出引用和恢复信息。

## 7. 状态退出门槛

```text
UNDERSTAND
  normalized query + attraction candidates + task type

RAG_RETRIEVE
  RetrievalReport（允许零结果）

EVIDENCE_EVALUATE
  ClaimDecision[] + CoverageReport

COMPOSE
  AnswerClaim[]，禁止仅返回自由文本

CITATION_GUARD
  每个保留事实 claim 都有有效 Evidence

DELIVER
  最终 response schema 通过
```

Gap Loop：

```text
RAG_RETRIEVE
  -> EVIDENCE_EVALUATE
      -> coverage sufficient -> COMPOSE
      -> coverage missing and gap_round=0 -> LIVE_GAP_FILL
      -> coverage missing and gap_round=1 -> LIMITED_ANSWER
```

## 8. 动态景点 RAG

RAG 只负责少量景点事实的动态管理，不追求大规模语料。

### 8.1 数据模型

```text
attraction
  attraction_id, canonical_name, city, country, aliases

source_document
  source_id, attraction_id, source_url, source_type, fact_types

document_version
  version_id, source_id, content_hash, retrieved_at
  valid_from, valid_to, status

fact_chunk
  chunk_id, version_id, attraction_id, fact_type
  content, locator, language, source_url

retrieval_log
  query_id, normalized_query, filters, returned_chunk_ids, scores
```

版本状态：

```text
pending -> active -> superseded
                 -> expired
pending -> rejected
```

事实类型限制为：

- `opening_hours`
- `ticket_price`
- `reservation`
- `transport`
- `accessibility`
- `visitor_notice`
- `general_description`

### 8.2 更新规则

- `source_url + attraction_id` 标识一个来源。
- hash 不变时不创建版本。
- 内容变化时创建新版本，并将旧版本标记为 `superseded`。
- 不同 fact type 使用不同 TTL，超期标记为 `expired`。
- 查询默认只检索 `active` 版本。
- 过期事实只能作为 candidate Evidence，不能支持强事实结论。
- 搜索摘要、论坛和模型先验只能进入 `pending`。
- 官方来源和结构化 API 通过确定性校验后可以自动发布。

### 8.3 查询与维护分离

```text
Entity Resolution
  -> attraction_id + fact_type filters
  -> SQLite FTS5 Top-K
  -> source quality + freshness rerank
  -> RAG chunks to Evidence
  -> Coverage
  -> missing/stale -> LIVE_GAP_FILL
```

实时工具结果先作为本次 run 的临时 Evidence。符合更新条件的结果写入 `pending`，由独立 refresh/publish 流程发布，避免查询路径污染知识库。

### 8.4 技术选择

- SQLite + FTS5，保证本地、CI 和 Eval 可复现。
- BM25 初筛，现有 source quality、freshness 和 claim policy rerank。
- 不增加独立向量数据库。
- 提供 `KnowledgeRepository` 和 `Retriever` 接口，保留替换 pgvector 的边界，但本项目不实现。
- 不开发知识库管理前端，只提供 CLI。

```powershell
python -m app.knowledge.cli seed evals/fixtures/attractions
python -m app.knowledge.cli refresh
python -m app.knowledge.cli publish --version-id <id>
python -m app.knowledge.cli inspect --attraction <name>
```

Evidence 增加 provenance：

```text
source_id
document_version_id
chunk_id
content_hash
locator
valid_from / valid_to
retrieval_score
```

最终引用链：

```text
AnswerClaim -> Evidence -> fact_chunk -> document_version -> source_url
```

## 9. 比较任务

比较任务为每个景点建立独立子作用域：

```text
COMPARISON
  |- RETRIEVE[attraction=A]
  `- RETRIEVE[attraction=B]
```

每个作用域拥有 `subtask_id`、coverage 和 failure。只有双方至少有一个相同 claim 维度时才能形成比较结论，否则进入 `LIMITED_ANSWER`。

## 10. 运行存储与 Replay

Agent Core Store 收敛为：

```text
run
phase_event
execution_attempt
evidence_record
answer_claim
citation_decision
run_metric
```

本项目不实现分布式任务恢复，只实现：

- `inspect --query-id`：查看完整运行轨迹。
- `replay --query-id --from evaluate`：复用已保存 Evidence，重新执行评估、合成和 Citation Guard。

## 11. 可观测性与服务边界

贯通字段：

```text
trace_id
session_id
query_id
phase
tool/provider
model_version
prompt_version
corpus_version
latency
token_usage
```

最低实现：

- Python 结构化 JSON 日志。
- Java 传递并持久化 `trace_id`。
- `RunMetrics` 写入 Agent Store，debug response 可返回。
- `/health/live` 检查进程。
- `/health/ready` 检查 LLM、RAG 数据库和必需工具配置。
- `debug=false` 时不写 debug markdown，不返回内部执行细节。
- 日志不记录 API key、JWT 和完整用户上下文。
- Java 到 Python 使用内部 service key。

## 12. Eval 语料

使用 8 个景点，每个景点维护 4 至 6 类事实：

```text
约 40 条 active fact chunks
约 12 条 superseded / expired chunks
约 8 条 conflicting / pending chunks
```

Eval 约 50 条：

| 数据集 | 数量 | 验证目标 |
| --- | ---: | --- |
| retrieval | 16 | 查询改写、Recall@K、MRR |
| versioning | 8 | 新版本、失效、过期泄漏 |
| state_routing | 8 | 三类任务和澄清路径 |
| evidence_conflict | 6 | 冲突、来源优先级、拒答 |
| multi_turn | 4 | session 和地点指代 |
| failure_recovery | 4 | timeout、429、空结果、解析失败 |
| comparison | 4 | 双景点 coverage 和公平比较 |

## 13. Eval 指标与门槛

RAG：

- Recall@3
- MRR
- active version accuracy
- expired chunk leakage rate
- source attribution accuracy

状态链：

- path accuracy
- illegal transition count
- recovery transition accuracy
- max-step termination rate
- clarification accuracy

Evidence：

- required claim coverage
- conflict detection precision/recall
- correct abstention rate
- source authority rate

答案：

- citation precision/recall
- unsupported hard fact rate
- claim value accuracy

运行：

- P50/P95 latency
- tool/retry count
- budget violation count
- replay consistency

目标门槛：

```text
RAG Recall@3                     >= 0.90
active version accuracy          = 1.00
expired chunk leakage            = 0
state path accuracy              >= 0.95
illegal transitions              = 0
citation precision               >= 0.95
unsupported hard facts           = 0
correct abstention rate          >= 0.90
replay claim-set consistency     = 1.00
```

## 14. 测试策略

1. 单元测试：StateHandler、TransitionTable、RAG 版本、Evidence 和 Citation。
2. 状态链集成测试：固定 Fake LLM、Fake Tool 和临时 SQLite，断言完整路径和审计事件。
3. Python API 端到端测试：FastAPI TestClient 调用真实状态机，只替换外部 adapter。
4. Java-Python 契约测试：验证 session、trace 和 response schema，增加真实两轮 session 场景。
5. Web：保留 build，并为 Evidence/Citation 渲染增加少量纯函数测试。

故障注入 adapter：

```text
fail_once(timeout)
always_empty
rate_limit_then_success
malformed_payload
return_stale_evidence
return_conflicting_evidence
```

每个故障必须断言恢复状态、审计事件、预算和最终出口。

## 15. Baseline 与实施顺序

```text
建立 fixture 和 characterization eval
  -> 运行当前 baseline
  -> 保存 baseline.json / baseline.md
  -> 裁剪与主链重构
  -> 运行 refactored eval
  -> 生成 comparison.md
```

每份报告记录：

```text
git_sha
dataset_version
corpus_version
model_version
prompt_version
tool_config_hash
metrics
failed_cases
```

CI：

- 每次提交运行无网络单元测试、状态链集成测试和快速 Eval。
- 真实 LLM 质量评测手动运行。
- README 只展示可复现离线指标，以及一次明确标注配置的真实模型评测。

## 16. 成功标准

- 仓库只宣传四项用户能力：事实查询、适合度、比较、澄清。
- Python 只有一个可达 orchestration runtime。
- 每个状态都有输入输出 gate、失败出口和审计事件。
- RAG 支持版本、失效、检索、来源追踪和离线指标。
- AnswerClaim 到来源 URL 的引用链可验证。
- 现有 Java/Web 平台能力不回退。
- 全部测试、快速 Eval 和构建命令通过。
- README 展示真实 baseline、重构结果和失败案例。
