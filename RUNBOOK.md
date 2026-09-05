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
- `AGENT_RUNTIME_PROFILE=offline`：默认不装配外部模型、地图与知识晋升；online 才启用有凭据的适配器。
- `LLM_COMPOSER_ENABLED=true`：仅 online 且有模型时启用一次受控组合；设 false 可关闭额外模型调用。
- `COMPOSER_TIMEOUT_SECONDS=2`：大于 0、最多 5 秒，短于 Compose 状态的 10 秒总期限。单次输出最多 512 tokens，无 repair/SDK 隐式重试；超时、非法 JSON、增删/重复 ID、服务故障均保留完整确定性模板，并记录具名失败与恢复事件。
- `BOUNDED_BAIDU_ENABLED=true`、`BAIDU_MAP_AK`：仅允许 search/detail；与旧 MCP_PROFILE 无关。
- `KNOWLEDGE_PROMOTION_ENABLED=true`：启用受控晋升旁支；`BAIDU_STORAGE_PERMITTED` 是独立的提供商数据留存许可，未确认必须 false。
- `INDEX_JOB_POLL_SECONDS`：持久索引待办的后台轮询间隔，默认 5 秒。

需要在线地图时，先在仓库的 `infra/baidu-mcp` 运行 `npm ci`，安装锁定的 Server 1.0.5。Python 使用 SDK 1.29.1；默认启动本地 entrypoint，不在请求中下载 npx latest。readiness 中 llm=configured 仅表示有配置，不表示真实调用成功。

Anthropic SDK 固定 0.104.1，HTTP transport 固定 httpx 0.28.1。2026-09-05 CI 曾因无上限 SDK 升级改用 httpx2、拒绝原 httpx.MockTransport 客户端而失败；当前使用经过真实 SDK 假 HTTP 测试的固定依赖对。未来升级需同时迁移客户端测试与 Eval transport，不能直接放开版本。

Composer 只获得已批准 Claim 的文本、ID、事实类型与景点/子任务绑定，最多 32 条、序列化输入 16000 字符；不发送原用户查询、会话历史或原始 MCP payload。它只组织展示顺序，不生成新的事实、标题或建议。常规地址 smoke 现在通常为理解/候选/Composer 共 3 次 LLM、2 次地图调用，仍受最多各 4 次上限控制；真实 smoke 会检查 model_composition。

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
也不会再次发布知识或同步索引；只生成新的 replay 审计。它固定原策略/时间快照，不是用新策略重新评估。缺完整 delivery snapshot 的旧 run 会返回 replay_snapshot_unavailable。

`promotion_summary` 和 `index_sync_status` 是回答交付时快照，历史回答不自动刷新。active 只代表 SQLite 发布，不能据此声称已索引；仅观察到成功 job 和 generation receipt 才显示 indexed。观察失败显示 unknown，不影响已验证的事实回答。

自动晋升的 pending job 在重启后仍可恢复，或手动执行：

```powershell
python -m app.evidence.knowledge.cli sync-pending --db ./data/knowledge.sqlite3 --qdrant-path ./data/qdrant --limit 10
```

普通人工 CLI publish 不自动创建 promotion outbox，仍需显式 reindex。后台与 CLI 不要同时打开同一个 Qdrant local 目录；管理操作前先停 Agent，或使用独立 server 模式。

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

## 真实验收（显式 opt-in）

真实语义检索只下载公开 embedding 模型并在本地计算，不调用收费 LLM/百度服务：

```powershell
python -m evals.runner --suite retrieval --profile real-embedding --report evals/reports/generated/resume-closure-semantic.json
```

首次需联网下载 BAAI/bge-small-zh-v1.5。缺模型/执行失败记录 blocked 并非零退出，不填写伪造指标。离线评测和真实语义结果是不同 profile。

真实 LLM/百度 smoke 需预先授权调用费用和临时数据处理，配置现有凭据；命令不能代表提供商已授予缓存许可：

```powershell
python -m evals.live_smoke --allow-live --allow-data-retention --max-tool-calls 4 --max-llm-calls 4 --report evals/reports/generated/live-smoke.json
```

仅查固定景点地址、严格限定调用数量，使用隔离临时数据库/本地索引，不改现有知识库；运行后清理临时数据。最终报告只含状态、计数、布尔验收结果与版本/数据集 hash，不保存原始响应、地址、prompt 或 key。该 smoke 用 deterministic index 验证真实连接，语义效果由独立 real-embedding 命令衡量。

不加两个 allow 标志时记录 not_run，不加载凭据；缺凭据/服务启动条件则 blocked。passed 返回 0，验收失败返回 1，not_run/blocked 返回 2。普通 CI 绝不传 allow 标志。

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
