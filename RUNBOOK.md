# Runbook

## 运行边界

| 组件 | 端口 | 责任 |
|---|---:|---|
| Web | 5173 | 只访问 Java API |
| Java Platform API | 8082 | 认证、会话、记录、收藏、Agent 网关 |
| Python Agent | 8001 | 一次可审计 Agent run |
| Qdrant | 6333 | 可选的稠密向量索引；SQLite 仍是事实权威 |

支持的产品行为仅有景点事实查询、适合度判断、双景点比较和必要澄清。行程、周边、评论挖掘、票务爬虫和人流估算不在运行范围内。

## 安装与配置

需要 Python 3.13、Java 21、Node.js 20；Docker 只在演示 Qdrant 服务边界时需要。

```powershell
cd apps/agent-python
pip install -r requirements.txt
copy .env.example .env

cd ../web
npm install
```

离线测试和默认本地运行不需要真实 LLM key。Python `.env` 中的重要设置：

- `AGENT_SERVICE_KEY`：Java 与 Python 必须一致。
- `KNOWLEDGE_DB_PATH`：SQLite 知识权威库。
- `AGENT_RUN_DB_PATH`：状态审计、Evidence、claim、引用决策和回放产物。
- `QDRANT_MODE=local`：进程内本地索引，最适合快速演示。
- `QDRANT_MODE=server`：连接独立 Qdrant；同时设置 URL 与 API key。
- `EMBEDDING_MODE=deterministic`：可重复的离线控制面验证，不代表真实语义质量。

Java 读取 `AGENT_BASE_URL` 和 `AGENT_SERVICE_KEY`：

```powershell
$env:AGENT_BASE_URL="http://127.0.0.1:8001"
$env:AGENT_SERVICE_KEY="change-me"
```

## 启动

如需独立 Qdrant：

```powershell
$env:QDRANT_API_KEY="local-dev-key"
docker compose -f infra/qdrant/compose.yml up -d
```

随后分别启动三个进程：

```powershell
# Terminal 1
cd apps/agent-python
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Terminal 2
cd apps/api-java
mvn spring-boot:run

# Terminal 3
cd apps/web
npm run dev
```

健康检查：

```powershell
curl.exe http://127.0.0.1:8001/agent/health/live
curl.exe http://127.0.0.1:8001/agent/health/ready
curl.exe http://127.0.0.1:8082/health
```

## 知识维护闭环

所有命令在 `apps/agent-python` 下执行。fixture 格式见 `evals/fixtures/knowledge.json`。

```powershell
# 导入并直接发布受控知识
python -m app.evidence.knowledge.cli seed `
  --db ./data/knowledge.sqlite3 `
  --fixture ./evals/fixtures/knowledge.json `
  --auto-publish

# 重新摄取指定来源；同内容幂等，修改 fixture 后生成 pending 版本
python -m app.evidence.knowledge.cli refresh `
  --db ./data/knowledge.sqlite3 `
  --source-id main-forbidden-city `
  --fixture ./evals/fixtures/knowledge.json

# 审核后发布；发布会原子 supersede 同一来源的旧 active 版本
python -m app.evidence.knowledge.cli publish `
  --db ./data/knowledge.sqlite3 `
  --version-id <version-id>

# 查看景点版本与当前索引 generation
python -m app.evidence.knowledge.cli inspect `
  --db ./data/knowledge.sqlite3 `
  --attraction forbidden-city `
  --index

# 从 SQLite 活动版本重建本地向量索引
python -m app.evidence.knowledge.cli reindex `
  --db ./data/knowledge.sqlite3 `
  --qdrant-mode local `
  --qdrant-path ./data/qdrant
```

独立 Qdrant 时把最后一条改为 `--qdrant-mode server --qdrant-url http://127.0.0.1:6333 --qdrant-api-key local-dev-key`。索引失败不会改变 SQLite 中的事实版本；稠密结果返回后还会由 SQLite 重新校验版本和内容哈希。

## 审计与回放

每次请求返回 `query_id`。用它检查逐状态 attempt、失败码、恢复动作、Evidence、claims 和引用决策：

```powershell
python -m app.orchestration.run_cli inspect `
  --db ./data/agent_runs.sqlite3 `
  --query-id <query-id>

python -m app.orchestration.run_cli replay `
  --db ./data/agent_runs.sqlite3 `
  --query-id <query-id> `
  --from-state evidence_evaluate
```

回放只消费已持久化产物，不重新调用检索或外部模型。

## 验证与发布门禁

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

真实 Qdrant 集成测试由 CI 启动带 API key 的 `qdrant/qdrant:v1.19.0`，再设置 `RUN_QDRANT_INTEGRATION=1` 执行。默认本地测试会跳过它。

## 常见问题

| 现象 | 排查 |
|---|---|
| Java 返回 `agent_unavailable` | 检查 `AGENT_BASE_URL`、Python `:8001` 和 `/agent/health/ready`。 |
| Python 返回 401 | 确保 Java/Python 的 `AGENT_SERVICE_KEY` 完全一致。 |
| readiness 显示 Qdrant 不可用 | 本地演示可用 `QDRANT_MODE=local`；server 模式检查容器、URL 和 API key。 |
| 稠密通道失败但仍有回答 | 查看 `retrieval_report.degradation`；设计允许降级到 lexical-only，引用门禁仍生效。 |
| 回答变成 limited/safe failure | 按 `query_id` inspect，定位 Evidence Evaluate 或 Citation Guard 的拒绝原因。 |
| 发布新知识后仍命中旧向量 | 执行 `reindex`；陈旧 point 会先被后过滤拒绝，不会进入答案。 |

本地数据库、Qdrant 数据、`dist/`、`target/`、缓存和调试输出均为 Git 忽略产物。Docker 配置只代表单机作品集，不宣称高可用、备份或灾备能力。
