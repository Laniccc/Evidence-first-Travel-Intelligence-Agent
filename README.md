# Evidence-first Travel Intelligence Agent

面向日本、中国、韩国的 **Evidence-first Travel Intelligence Agent**。

> **当前版本：Mock MVP + Real Data Pilot（小范围真实数据）**  
> 默认 `TOOL_MODE=hybrid`：优先真实 Weather / Places / 官方白名单页面；失败、超时或缺少 API key 时回退 mock。  
> 开放时间、票价、交通、评价等仍以 **mock tools** 为主；天气与地点在配置密钥后可走真实 API。  
> 所有事实经 **Evidence 链路**聚合后生成回答，**不来自 LLM 训练记忆**；未配置真实 API 时行为与 Mock MVP 一致。

**运维手册**：[RUNBOOK.md](RUNBOOK.md)（安装、API 示例、故障排查）

> **Monorepo**：运行时以 `apps/agent-python`、`apps/api-java`、`apps/web` 为准；`backend/` 为 **LEGACY** 只读对照，详见 [backend/LEGACY.md](backend/LEGACY.md)。

---

## 架构与端口

```text
浏览器 (:5173)
  → apps/web          Vite dev / dist 静态页
  → POST /api/travel/query
       → apps/api-java (:8080)   session、Tool Gateway
            → POST /agent/query
                 → apps/agent-python (:8001)   Agent 核心
                      → packages/tools
```

| 组件 | 端口 | 说明 |
|------|------|------|
| [apps/web](apps/web/) | 5173 | 前端 UI（Vite） |
| [apps/api-java](apps/api-java/) | 8080 | Java API Gateway |
| [apps/agent-python](apps/agent-python/) | 8001 | Python Agent（`/agent/health`、`/agent/query`） |

各应用详细说明见对应目录下的 README。

---

## 快速开始（推荐：Conda）

### 1. Python Agent（必须）

```powershell
conda activate ClaudeAgent          # 或你的 conda 环境名
cd apps/agent-python
pip install -r requirements.txt
copy .env.example .env
notepad .env                        # 建议先设 LLM_MODE=mock

$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

健康检查：http://127.0.0.1:8001/agent/health  
（`:8001/` 根路径无页面，404 正常。）

详见 [apps/agent-python/README.md](apps/agent-python/README.md)。

### 2. 前端（可选，需 Node.js）

**完整链路**（需 Maven，启动 api-java）：

```powershell
# 终端 2：api-java（需已安装 Maven）
cd apps/api-java
mvn spring-boot:run

# 终端 3：前端
cd apps/web
copy .env.example .env
npm install
npm run dev
```

打开 http://127.0.0.1:5173

**无 Maven 时临时绕过 Java**（仅 web + agent-python）：

1. 保持终端 1 的 agent-python 运行（8001）
2. 按 [apps/web/README.md — 临时绕过 api-java](apps/web/README.md#临时绕过-api-java无-maven) 修改 `vite.config.js` 代理
3. `cd apps/web && npm run dev` → http://127.0.0.1:5173

此时无 Java 会话记忆与 Tool Gateway；测完请恢复 Vite 默认代理。

### 3. LLM 配置（可选）

在 `apps/agent-python/.env`：

```env
LLM_MODE=anthropic
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-v4-flash
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
```

离线演示可设 `LLM_MODE=mock`（不调用 LLM，evidence 链路仍完整）。

### 4. API 示例（PowerShell，UTF-8）

Windows PowerShell 发中文 JSON 易乱码，推荐：

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$json = '{"query":"京都清水寺适合带父母去吗？","session_id":"demo-session"}'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/agent/query `
  -ContentType "application/json; charset=utf-8" `
  -Body $bytes
```

更多 curl / 文件方式见 [apps/agent-python/README.md](apps/agent-python/README.md)。

---

## Agent 回答链路（主流程）

![证据优先 Travel Agent 当前状态流程图](image.png)

```text
User Query
  → ConversationContextBuilder
  → QueryUnderstandingPromptState → SemanticFrame
  → AnswerModeRouter（EvidencePolicy + 工具能力）
  → 分支：clarification | evidence_required | model_prior | estimation
  → ToolRouter / KnowledgePriorTool → Evidence
  → EvidenceAggregator
  → ReviewMining / Scorer（景点级问题）
  → Composer
  → CitationChecker
```

系统**不再**为每类问题堆叠固定 template 或大量关键词 if-else。  
`QueryUnderstanding` 产出通用 **SemanticFrame**；**AnswerModeRouter** 决定是否需要工具证据、是否允许 **model prior**；**KnowledgePriorTool** 将低置信度常识建议包装为 `Evidence`（`source_type=model_prior`），Composer 仍只读 Evidence 作答。

**精确实时事实**（开放时间、票价、今日天气、实时人流）必须 `evidence_required`，禁止 model prior。

### 用户需求理解层（LLM-first）

主路径：**LLMUnderstandingState → LLMUnderstandingSubAgent → NormalizedUserRequest JSON → S3 AnswerModeRouter**。

实现位于 `apps/agent-python/app/`（prompts、agents、orchestrator）。

### Capability-based Tool Router

用户问的是**信息需求**（人流、适老、天气），不是工具名。链路先把自然语言转成 `TravelTask` + `InformationNeed`，再由 `ToolRouter` 按 **capabilities** 动态选工具。工具真相源：`packages/tools/`。

---

## Real Data Pilot（真实数据试点）

首期接入 **Weather / Places / 官方白名单页面** 及 **MCP adapter 占位**。真实 API 响应必须先归一化为 `Evidence[]`；Composer / Scorer / CitationChecker **不得**直接读取原始 response。

配置项在 `apps/agent-python/.env`（与 legacy `backend/.env` 字段对齐）：

```env
TOOL_MODE=hybrid
ENABLE_REAL_WEATHER=false
ENABLE_REAL_PLACES=false
ENABLE_REAL_OFFICIAL_PAGE=false
MCP_ENABLED=false
REAL_TOOL_TIMEOUT_SECONDS=8
REAL_TOOL_CACHE_TTL_SECONDS=3600
```

| 能力 | 启用示例 |
|------|----------|
| Weather | `ENABLE_REAL_WEATHER=true` + `WEATHER_API_KEY`（[OpenWeatherMap](https://openweathermap.org/api)） |
| Places | `ENABLE_REAL_PLACES=true` + `PLACES_API_KEY=pilot`（Nominatim 试点） |
| 官方页 | `ENABLE_REAL_OFFICIAL_PAGE=true`（白名单见 `app/config.py`） |
| MCP | `MCP_ENABLED=true`（需 api-java Tool Gateway 时配合 Java 层） |

评测用例仍在 `backend/app/evals/`（迁移至 `tests/evals/` 进行中）。

---

## 目录结构

```text
Evidence-first Travel Intelligence Agent/
├── apps/
│   ├── agent-python/     # Python Agent 核心（运行时主入口）
│   ├── api-java/         # Java API Gateway (:8080)
│   └── web/              # 前端 Vite SPA (:5173)
├── contracts/            # 跨语言 JSON Schema
├── packages/
│   └── tools/            # 工具注册、Mock/Real/Hybrid（真相源）
├── backend/              # LEGACY — 只读对照，勿新增功能
├── README.md
├── RUNBOOK.md
└── REPO_MAP.md / MIGRATION_PLAN.md
```

完整职责映射：[REPO_MAP.md](REPO_MAP.md)。

---

## 运行评测

```powershell
conda activate ClaudeAgent
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/ -q

# Legacy 对照（backend 内 evals，可选）
cd backend
pytest app/evals -q
```

---

## 故障排查

| 现象 | 处理 |
|------|------|
| `ModuleNotFoundError: No module named 'app'` | 在 `apps/agent-python` 下运行，并设置 `$env:PYTHONPATH = (Get-Location).Path` |
| `:8001/` 返回 404 | 正常；使用 `/agent/health` 或前端 `:5173` |
| 端口 8001 占用 | 结束旧 uvicorn 进程，或换 `--port` |
| PowerShell 中文乱码 / JSON 解析失败 | 见 [apps/agent-python/README.md](apps/agent-python/README.md) UTF-8 示例 |
| 前端无法连 API | 确认 api-java (:8080) 或已配置 Vite 临时绕过 Java |
| 回答过于模板化 | 检查 `LLM_MODE=mock`；配置 API Key 后设 `LLM_MODE=anthropic` |
| 真实天气未生效 | 确认 `ENABLE_REAL_WEATHER=true` 且 key 已设置；查看 `tool_traces` 是否 `fallback_used` |

更多见 [RUNBOOK.md §11 故障排查](RUNBOOK.md)。

---

## 当前限制

- 重点支持 **日本、中国、韩国**；景点库覆盖有限
- 数据以 **mock** 为主；真实试点仅 weather / places / 官方白名单
- **实时人流、排队、地图热力** 尚未接入；当前为评价 / 代理估算
- **CitationChecker** 为规则级检测，非完美事实验证
- 完整三件套需 Maven；本地可临时绕过 Java 仅测 Agent + 前端

---

## 设计原则

- Evidence-first / Source-aware / Conflict-aware / Persona-aware
- State-machine constrained
- 无法证实的内容通过 `limitations` 或降低 `confidence` 表达

## Legacy 回退

紧急对照或回退旧单体：

```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

详见 [backend/LEGACY.md](backend/LEGACY.md)。**新功能请勿写入 `backend/`。**
