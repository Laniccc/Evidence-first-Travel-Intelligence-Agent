# Evidence-first Travel Intelligence Agent

一个面向企业级 Agent 开发实习的可运行作品集：用显式状态链处理每一环错误，用版本化 Hybrid RAG 动态管理景点事实，并在交付前用 Evidence/Citation 门禁阻止无来源硬事实。

项目刻意只保留四类产品行为：景点事实查询、适合度判断、双景点比较和必要澄清。行程生成、周边推荐、评论挖掘、票务爬虫和人流估算已经物理裁剪；`ticket_price` 作为知识库事实保留。

## 技术闭环

```text
Web 工作台
  → Java Spring Boot：认证、会话、历史、收藏、Agent 服务边界
    → Python FastAPI：单次 Agent run
      → Understand → Route → Retrieval Plan → Hybrid Retrieve
      → Evidence Evaluate → Compose → Citation Guard → Deliver
                           ↘ bounded live gap-fill ↗
                           ↘ Knowledge Promote → SQLite + durable index job

SQLite/FTS5（事实与版本权威） → Qdrant（可重建稠密索引）
              ↑ Evidence provenance / version / content hash
```

核心设计：

- 可审计状态链：每个状态都有输入/输出契约、超时/重试边界、失败码、恢复策略和合法转换检查。
- 动态知识治理：pending → active → superseded/expired/rejected；发布新版本时旧版本原子失效。
- Hybrid RAG：SQLite FTS5 + Qdrant dense + RRF + 元数据/版本/哈希后过滤 + 权威度重排。
- Evidence-first：回答拆成 typed `AnswerClaim`；硬事实必须关联活动版本 Evidence 和来源 URL。
- 轻量 LLM Composer：online 模式下最多一次、默认 2 秒的 Claim 顺序提议；严格 JSON 必须完整保留全部已批准 Claim ID。代码恢复原事实与引用，非法输出或模型故障回退 Evidence 模板，再经过 Citation Guard。
- 真实运营错误控制：并行双通道独立降级、一次逻辑 gap task（search/detail 各最多 2 次，共 4 次 tools/call）、冲突保留、证据不足拒答、无外部写副作用的原产物 Replay。
- Evidence-to-Knowledge：模型候选经过 Schema/Grounding/Provenance/Temporal/Persistence Policy 校验；经留存许可的稳定地址可发布，开放时间仅待审核。发布与索引任务同事务，索引失败可恢复。
- 公开观测：区分候选拒绝、待审核、已发布但索引待同步与已索引；Java 保留快照与安全失败，Web 只投影允许字段。
- 平台边界：Java 持有用户和业务数据；Python 只拥有一次 Agent run；服务间使用 API key、trace id 和强类型错误契约。

详细设计见 [状态链](docs/architecture/STATE_CHAIN.md)、[知识生命周期](docs/architecture/KNOWLEDGE_LIFECYCLE.md)、[Hybrid Retrieval](docs/architecture/HYBRID_RETRIEVAL.md) 和 [Eval](docs/architecture/EVALS.md)。

## Eval 结果

扩展离线门禁包含 112 个案例，21 项数值门禁及逐案例安全检查通过（保留原 71 个案例和 13 项门槛）：

| 关键指标 | 结果 | 门槛 |
|---|---:|---:|
| Recall@3 / MRR / nDCG@5 | 1.00 / 1.00 / 1.00 | ≥ .90 / .85 / .90 |
| Metadata filter accuracy | 1.00 | = 1.00 |
| Expired/superseded leakage | 0 | = 0 |
| State path accuracy / illegal transitions | 1.00 / 0 | ≥ .95 / = 0 |
| Stale vector rejection / index rebuild consistency | 1.00 / 1.00 | = 1.00 |
| Unsupported hard facts | 0 | = 0 |
| Citation / abstention precision | 1.00 / 1.00 | ≥ .95 / .90 |
| Replay consistency | 1.00 | = 1.00 |
| Unsafe auto publish / provenance fabrication / MCP budget violations | 0 / 0 / 0 | = 0 |
| Promotion idempotency / sync recovery / miss-promote-dense hit | 1 / 1 / 1 | = 1 |
| Replay external calls / knowledge write side effects | 0 / 0 | = 0 |

离线报告列出四组消融，使用 deterministic hash embedding 验证编排与安全，不代表语义效果。另用 BAAI/bge-small-zh-v1.5 实测 28 个检索案例：Recall@3 **96.43%**、MRR **97.14%**、nDCG@5 **97.81%**。无障碍同义提问有一例仅排第 5；小型受控集不是线上准确率，也未证明相对词法检索的语义增益。查看[验收记录](docs/plans/2026-09-04-batch-d-final-verification.md)。

实际 LLM/百度服务验收仍为 **not_run**：目前完成生产接线与离线协议验证，不能将假服务测试写成真实服务已验收。

## 快速运行

需要 Python 3.13、Java 21、Node.js 20；Qdrant 可使用本地模式，也可启动 Docker 服务。

```powershell
# 安装
cd apps/agent-python
pip install -r requirements.txt
copy .env.example .env

cd ../web
npm install

# 可选：Qdrant 单机服务
cd ../..
docker compose -f infra/qdrant/compose.yml up -d
```

分别启动三个进程：

```powershell
# Python Agent :8001
cd apps/agent-python
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Java Platform :8082
cd apps/api-java
$env:AGENT_SERVICE_KEY="change-me"
mvn spring-boot:run

# Web :5173
cd apps/web
npm run dev
```

Web 只访问 Java；Java 通过 `POST /agent/query` 调用 Python。Python 另提供 `/agent/health/live` 与 `/agent/health/ready`。

## 一键验证

```powershell
cd apps/agent-python
python -m pytest -q
python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/final-offline.json

cd ../api-java
mvn test

cd ../web
npm test
npm run build

cd ../..
docker compose -f infra/qdrant/compose.yml config
```

GitHub Actions 分成 Python+offline Eval、真实 Qdrant 服务边界、Java、Web 四个 job；CI 不调用真实 LLM 或下载 embedding model。

## 仓库结构

| 路径 | 责任 |
|---|---|
| `apps/agent-python` | 状态机、知识治理、检索、Evidence/Citation、审计与 Eval |
| `apps/api-java` | 用户、认证、会话、查询记录、收藏、Python Agent client |
| `apps/web` | Evidence、版本、检索降级、引用决策和状态审计展示 |
| `infra/qdrant` | 带 API key 的单机 Qdrant 作品集配置 |
| `docs/architecture` | 状态链、知识生命周期、检索和 Eval 设计说明 |

Qdrant Docker 方案仅是单机作品集实现，不宣称 HA、备份、容灾或生产集群能力。运维命令见 [RUNBOOK.md](RUNBOOK.md)，具体入口见 [REPO_MAP.md](REPO_MAP.md)。
