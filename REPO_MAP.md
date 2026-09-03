# Repository Map

## 运行入口

| 区域 | 入口 | 责任 |
|---|---|---|
| Python Agent | `apps/agent-python/app/main.py` | FastAPI 生命周期与依赖装配 |
| Python API | `apps/agent-python/app/api/routes.py` | `/agent/query`、liveness、readiness 和服务密钥边界 |
| 状态机 | `apps/agent-python/app/orchestration/state_machine.py` | 唯一生产状态链 |
| 转换规则 | `apps/agent-python/app/orchestration/transition_table.py` | 合法状态边集合 |
| 审计/回放 | `apps/agent-python/app/orchestration/state_audit.py`, `run_cli.py` | 状态事件、检查和 artifact-only replay |
| Java Platform | `apps/api-java/src/main/java/com/travel/intelligence/api/ApiJavaApplication.java` | 平台进程入口 |
| Java Agent client | `apps/api-java/src/main/java/com/travel/intelligence/api/agent/infrastructure/PythonAgentClient.java` | trace id、服务密钥、强类型错误的 Python 边界 |
| Web | `apps/web/src/main.js` | 认证后的工作台 |
| Web result projection | `apps/web/src/presentation/agent-result.js` | Evidence、引用、版本、降级与审计视图 |

## Python 能力所有者

| 包 | 责任 |
|---|---|
| `api` / `contracts` | HTTP 边界与 Java-Python DTO |
| `context` / `understanding` | 会话解析、意图、实体和语义框架 |
| `planning` | fact/suitability/comparison 的检索计划与子任务隔离 |
| `evidence.knowledge` | SQLite 事实、版本、生命周期和维护 CLI |
| `evidence.retrieval` | lexical、dense、RRF、后过滤、重排和 RetrievalReport |
| `evidence` | 冲突、覆盖率、claim 决策和引用校验 |
| `execution` / `tools` / `integrations` | 有界工具执行、外部适配器和 Qdrant client |
| `composition` | typed AnswerClaim、确定性降级和响应投影 |
| `orchestration` | 状态运行时、审计、预算、持久化与回放 |
| `governance` / `observability` | 失败分类、安全、发布门禁、日志和 trace |

## 知识与 Eval

| 路径 | 用途 |
|---|---|
| `apps/agent-python/app/evidence/knowledge/schema.sql` | SQLite 权威 schema |
| `apps/agent-python/app/evidence/knowledge/cli.py` | seed、refresh、publish、inspect、reindex |
| `apps/agent-python/app/integrations/qdrant/vector_index.py` | 可重建稠密索引适配器 |
| `apps/agent-python/evals/datasets/` | 71 个确定性回归案例 |
| `apps/agent-python/evals/graders/` | 检索、版本、状态、恢复、Evidence、引用和一致性评分 |
| `apps/agent-python/evals/runner.py` | 消融、报告和 fail-on-regression 入口 |
| `apps/agent-python/evals/reports/final-offline.*` | 受版本控制的最终结果 |
| `.github/workflows/verify.yml` | Python/Eval、真实 Qdrant、Java、Web CI |

## Java 所有权

Java 的 `user`、`platform`、`agent`、`tool` 按领域优先，再分 `web`、`application`、`domain`、`infrastructure`。Java 持有用户、认证、会话、查询记录、收藏和未来商业数据；Python 只持有一次 Agent run。

## 已裁剪边界

运行时不再包含行程生成、周边推荐、评论挖掘、票务爬虫、人流估算或 Neo4j/Graph-RAG。`ticket_price` 仅作为可版本化事实类型保留。`test_removed_capabilities_gate.py` 会扫描 import、动态 import、配置、registry 和 route，防止这些能力回流。

`app.agents`、`app.orchestrator`、`app.schemas`、`app.tool_gateway`、`app.storage`、`app.catalog`、`app.prompts`、`app.policies` 已退役，不得重新创建。`app.contract` 只允许重导出 `app.contracts` 的公共契约。

## 验证入口

- Python：`python -m pytest -q`
- 全量 Eval：`python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/final-offline.json`
- Java：`mvn test`
- Web：`npm test` 与 `npm run build`
- Qdrant 配置：`docker compose -f infra/qdrant/compose.yml config`
