# Evidence-first Travel Intelligence Agent

面向日本、中国、韩国的 **Evidence-first Travel Intelligence Agent**。

> **当前版本：Mock MVP + Real Data Pilot（小范围真实数据）**  
> 默认 `TOOL_MODE=hybrid`：优先真实 Weather / Places / 官方白名单页面；失败、超时或缺少 API key 时回退 mock。  
> 开放时间、票价、交通、评价等仍以 **mock tools** 为主；天气与地点在配置密钥后可走真实 API。  
> 所有事实经 **Evidence 链路**聚合后生成回答，**不来自 LLM 训练记忆**；未配置真实 API 时行为与 Mock MVP 一致。

**安装、启动、配置与故障排查** → [RUNBOOK.md](RUNBOOK.md)

> **Monorepo**：运行时以 `apps/agent-python`、`apps/api-java`、`apps/web` 为准；`backend/` 为 **LEGACY** 只读对照，详见 [backend/LEGACY.md](backend/LEGACY.md)。

---

## 系统架构

```text
浏览器 (:5173)
  → apps/web              前端 SPA（Vite）
  → POST /api/travel/query
       → apps/api-java (:8080)     session、Tool Gateway、对外 REST
            → POST /agent/query
                 → apps/agent-python (:8001)   状态机、agents、Composer
                      → packages/tools        Mock / Real / Hybrid 工具
```

| 组件 | 职责 |
|------|------|
| [apps/web](apps/web/) | 旅行问答 UI；展示 answer、trace、evidence、limitations |
| [apps/api-java](apps/api-java/) | API Gateway；会话；可选 MCP / 工具转发 |
| [apps/agent-python](apps/agent-python/) | Agent 核心；Evidence-first 状态机 |
| [packages/tools](packages/tools/) | 工具注册与实现（项目内真相源） |
| [contracts/](contracts/) | 跨语言 JSON Schema（Request / Response） |
| [backend/](backend/) | **LEGACY** 旧单体，仅对照与紧急回退 |

完整目录职责：[REPO_MAP.md](REPO_MAP.md)。

---

## 设计原则

- **Evidence-first**：工具返回 `Evidence` → 聚合 → Composer **只读 Evidence** 生成回答
- **Source-aware / Conflict-aware**：记录来源、冲突与字段级证据
- **Persona-aware**：结合用户画像（同行人、节奏、预算等）调整信息需求
- **State-machine constrained**：编排由状态机约束，非开放式 Agent 自由发挥
- **诚实表达不确定性**：无法证实的内容写入 `limitations` 或降低 `confidence`
- **禁止 LLM 编造事实**：开放时间、票价、实时天气等不得来自模型训练记忆

---

## Agent 回答链路

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
`QueryUnderstanding` 产出通用 **SemanticFrame**；**AnswerModeRouter** 按问题类型决定是否需要工具证据、是否允许 **model prior**。

| 模式 | 含义 |
|------|------|
| `clarification` | 信息不足，向用户追问 |
| `evidence_required` | 必须有工具证据（精确实时事实） |
| `model_prior` | 允许常识型 prior，但须包装为 `Evidence`（`source_type=model_prior`） |
| `estimation` | 在证据不足时做有标注的估算 |

**精确实时事实**（开放时间、票价、今日天气、实时人流）必须走 `evidence_required`，禁止 model prior。

### 用户需求理解层（LLM-first）

主路径：

```text
LLMUnderstandingState
  → LLMUnderstandingSubAgent
  → NormalizedUserRequest JSON
  → S3 AnswerModeRouter
```

S2 子代理提示词（`app/prompts/llm_understanding.*.md`）按 **S3 路由契约** 设计：一次输出 `query_scope`、`country`、`answer_policy` 等字段；下游 adapter **仅做映射**，不再推断 scope/country。

### Capability-based Tool Router

用户表达的是**信息需求**（人流、适老、天气），不是工具名。链路先将自然语言转为 `TravelTask` + `InformationNeed`，再由 `ToolRouter` 按 **capabilities** 动态选工具：

| 用户问题 | 典型工具组合 |
|---------|-------------|
| 这里人流量怎么样？ | `reviews` + `places` + `fallback` |
| 故宫今天人多吗？ | 同上 + `weather` + `reservation_policy` |
| 适合带爸妈吗？ | `reviews` + `transit` + `official` + `restaurant` |

**人流量**：当前无实时人流 API，使用评价 + 地图代理 + fallback，回答中标注估算性质。

---

## 功能范围

- **单景点情报卡**：适老、人流、交通、开放信息等
- **多景点比较**：基于证据的对比与推荐
- **轻量行程建议**：结合用户上下文的一日/半日安排
- **可追溯输出**：`visible_trace`、`evidence_summary`、`field_evidence_summary`、`tool_traces`、`citation_check_result`
- **首期区域**：日本、中国、韩国（Region Gate 设计约束）

### API 响应字段（契约摘要）

与 [contracts/](contracts/) 及 `TravelQueryResponse` 对齐：

| 字段 | 说明 |
|------|------|
| `answer` | 自然语言回答 |
| `structured_result` | 推荐 / 比较 / 行程等结构化结果 |
| `visible_trace` | 用户可理解的执行轨迹 |
| `evidence_summary` | 证据来源摘要 |
| `field_evidence_summary` | 字段级 value + source_ids + confidence |
| `conflicts` | 来源冲突记录 |
| `limitations` | 限制与假设 |
| `confidence` | 整体置信度 |
| `tool_traces` | 工具调用轨迹（含 fallback 标记） |
| `citation_check_result` | 引用校验结果 |
| `semantic_frame_summary` | 语义理解摘要 |
| `answer_mode` | 最终路由模式 |

---

## Real Data Pilot（真实数据试点）

在 Mock MVP 之上，小范围接入真实外部数据；所有真实 API 响应**必须先归一化为 `Evidence[]`**，Composer / Scorer / CitationChecker **不得**直接读取原始 response。

### 工具模式 `TOOL_MODE`

| 值 | 行为 |
|----|------|
| `mock` | 仅 mock 工具 |
| `real` | 优先真实工具；失败仍回退 mock |
| `hybrid`（默认） | 先调 real；超时 / 失败 / 缺 key 时 fallback mock，并在 `limitations` 与 `tool_trace` 标记 `fallback_used=true` |

### 试点能力

| 能力 | 数据源 | 说明 |
|------|--------|------|
| Weather | OpenWeatherMap | 配置 key 后可走真实天气 |
| Places | OpenStreetMap Nominatim | 试点；`PLACES_API_KEY` 作启用开关 |
| 官方页 | 白名单 URL | 仅政府 / 官方旅游站，非全网爬虫 |
| MCP adapter | api-java Tool Gateway | 占位：`weather_mcp`、`places_mcp` 等 |

### 架构要点

- **Catalog 层**：`place_catalog` 隔离 mock 数据与回答层
- **Hybrid 工具链**：`HybridTravelTool` + TTL 缓存，`cache_hit` 记入 trace
- **Tool 抽象**：`BaseTravelTool` → `Evidence[]` → `PlaceFactSheet` → Composer

### 数据合规

- 当前**不建议**大规模评论抓取
- 评论平台、OTA 需单独处理 **ToS 与授权**
- 不绕过登录、验证码、反爬；不大规模爬取网页

环境变量与启用步骤见 [RUNBOOK.md § 配置](RUNBOOK.md#4-配置)。

---

## 目录结构（逻辑视图）

```text
Evidence-first Travel Intelligence Agent/
├── apps/
│   ├── agent-python/     # Python Agent 核心
│   ├── api-java/         # Java API Gateway
│   └── web/              # 前端 Vite SPA
├── contracts/            # 跨语言 JSON Schema
├── packages/tools/       # 工具真相源
├── backend/              # LEGACY（勿新增功能）
├── README.md             # 本文档：设计与功能
├── RUNBOOK.md            # 运维：安装、启动、排错
└── REPO_MAP.md
```

---

## 当前限制

- 重点支持 **日本、中国、韩国**；景点库覆盖有限
- 数据以 **mock** 为主；真实试点仅 weather / places / 官方白名单
- **实时人流、排队、地图热力** 尚未接入
- **CitationChecker** 为规则级检测，非完美事实验证
- 评测用例部分仍在 `backend/app/evals/`（迁移至 `tests/evals/` 进行中）

---

## 相关文档

| 文档 | 内容 |
|------|------|
| [RUNBOOK.md](RUNBOOK.md) | 环境、安装、启动、API 示例、评测、故障排查、GitHub 上传 |
| [REPO_MAP.md](REPO_MAP.md) | Monorepo 职责映射 |
| [backend/LEGACY.md](backend/LEGACY.md) | Legacy 单体说明 |
| [apps/agent-python/README.md](apps/agent-python/README.md) | Agent 服务细节 |
| [apps/web/README.md](apps/web/README.md) | 前端与 Vite 代理 |
