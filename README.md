# Evidence-first Travel Intelligence Agent

面向日本、中国、韩国的 **Evidence-first Travel Intelligence Agent** MVP。系统通过 mock/real 工具收集结构化 `Evidence`，再经状态机、评价挖掘、画像评分与 Composer 生成可追溯回答。

**完整运维说明见 [RUNBOOK.md](RUNBOOK.md)**（安装、配置、API、评测、GitHub 上传）。

## 功能范围（MVP）

- 单景点情报卡（官方信息 / 交通 / 天气 / 评价 / 画像评分）
- 多景点比较（并行检索 + 比较表 + 排序）
- 轻量一日/半日行程建议
- `visible_trace` / `evidence_summary` / `conflicts` / `limitations`
- Golden queries 基础评测

## 快速开始

### 1. 安装依赖

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

### 2. 启动 API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 调用示例

```bash
curl -X POST http://127.0.0.1:8000/api/travel/query ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"京都清水寺适合带父母去吗？\",\"user_context\":{\"party\":[\"elderly\"],\"pace\":\"relaxed\"}}"
```

```bash
curl http://127.0.0.1:8000/api/travel/supported-regions
```

## 目录结构

```text
backend/
  app/
    main.py                 # FastAPI 入口
    config.py               # 配置
    llm_client.py           # Claude SDK 封装（无 key 时 mock）
    orchestrator/
      state_machine.py      # S0-S12 状态链
      policies.py           # SourcePriorityPolicy
      confidence.py
      trace.py
    agents/
      intent_agent.py
      place_research_agent.py
      review_mining_agent.py
      suitability_scorer.py
      composer_agent.py
    tools/
      mock_data.py          # 东亚三国 mock 景点库
      *_tool.py             # MockOfficial/Review/Weather/Transit/Places...
    schemas/
    evals/
      golden_queries.json
```

## 状态链

`TravelAgentStateMachine` 实现：

`Region Gate → Intent → Context → Query Plan → Source Selection → Retrieval → Validation → Normalization → Conflict Detection → Review Mining → Suitability Scoring → Compose → Citation Check`

## 替换真实 API

1. 在 `app/tools/` 新增真实 tool，实现 `BaseTool.run()` 并返回 `Evidence`
2. 在 `ToolRegistry` 中注入真实 tool 替代 mock
3. 配置 `.env`：

```env
ANTHROPIC_API_KEY=sk-...
LLM_MODE=anthropic
```

4. 为地图/天气/交通/评论配置各自 API key（可在 `config.py` 扩展）

原则：**工具产 evidence，Composer 只基于 evidence 总结，禁止 LLM 直接编造开放时间/票价/路线。**

## 新增国家/城市/景点

1. 在 `app/tools/mock_data.py` 的 `PLACE_REGISTRY` / `PLACE_ALIASES` 添加条目
2. 在 `config.py` 的 `supported_cities` 添加城市
3. 在 `IntentAgent.COUNTRY_KEYWORDS` 添加识别词
4. 在 `evals/golden_queries.json` 增加验收样例

## 运行评测

```bash
cd backend
pytest app/evals -q
```

## 设计原则

- Evidence-first：关键结论必须可追溯到 Evidence
- Source-aware / Conflict-aware / Persona-aware
- State-machine constrained：工具调用由状态链控制
- East Asia first：日本 / 中国 / 韩国

## 后续扩展

- PostgreSQL + pgvector 持久化 evidence
- Redis 缓存
- Next.js Evidence Panel / Trace Timeline 前端
- 真实 MCP servers：`destination_mcp`, `review_mcp`, `weather_mcp` 等
- 复杂行程规划、长期记忆、购票跳转

## 限制说明

当前为 MVP mock 阶段：

- 景点库覆盖有限
- 天气/交通/评论为 mock 或摘要级数据
- 未接入真实 OTA/评论全文存储
- 无 key 时 LLM 使用 deterministic mock，不影响 evidence 链路演示

## 上传 GitHub

```powershell
.\upload_to_github.ps1 -DryRun   # 预览
.\upload_to_github.ps1           # 提交并推送
```

凭据配置与故障排查见 [RUNBOOK.md §12](RUNBOOK.md#12-上传项目到-github)。
