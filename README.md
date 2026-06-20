# Evidence-first Travel Intelligence Agent

面向日本、中国、韩国的 **Evidence-first Travel Intelligence Agent**。

> **当前版本：Mock MVP** — 不是真实旅游查询系统。  
> 开放时间、票价、交通、天气、评价等均来自 **mock tools**（`backend/app/tools/mock/`），经证据链路聚合后生成回答；**不来自 LLM 训练记忆**。  
> 接入真实 API 前请勿将输出当作真实票务/开放信息。

**运维手册**：[RUNBOOK.md](RUNBOOK.md)

## Agent 回答链路（主流程）

```text
User Query
  → ConversationContextBuilder
  → QueryUnderstandingPromptState（固定进入）
  → TravelTask
  → ClarificationGate（如需澄清则直接返回，不调用工具）
  → TravelTaskToUserGoalAdapter
  → RegionGate（优先 TravelTask.country/city）
  → InformationNeedPlanner
  → ToolRouter
  → TravelToolRegistry.run_tool / ToolTrace（每请求 clear_traces，统一记录 evidence_ids / latency / status）
  → Evidence
  → EvidenceAggregator
  → ReviewMining
  → Scorer
  → Composer
  → CitationChecker
```

**QueryUnderstandingPromptState 不是最终回答器**——它只做需求转写与 `TravelTask` 生成，不生成开放时间/票价/天气/人流等事实。  
`IntentAgent` 仅在 QueryUnderstanding 置信度低且无可用 TravelTask 时作为 fallback。  
`SourceSelectionPolicy` 仅作为 ToolRouter 无匹配需求时的兜底，不再是主链路入口。

### 用户需求理解层

| 组件 | 职责 |
|------|------|
| `ConversationContext` | 会话级上下文（`last_places`、`last_travel_date`、画像） |
| `ConversationContextBuilder` | 从 request / `conversation_memory` 构建上下文 |
| `QueryUnderstandingAgent` | 受控子代理：改写 + 指代 + TravelTask |
| `RuleBasedUnderstanding` | 离线规则解析（置信度 ≥0.75 时优先） |
| `QueryUnderstandingPromptState` | 状态机固定 state，写入 `visible_trace` |
| `TravelTaskToUserGoalAdapter` | TravelTask → UserGoal（主路径） |
| `ClarificationGate` | `needs_clarification=true` 时暂停工具调用 |
| `TravelToolRegistry` | 统一 `run_tool` / `record_skipped_tool`，每请求 `clear_traces`，输出 `tool_traces` |

**表达处理示例：**

- 「这里」「那边」「刚才那个」→ 从 `conversation_context.last_places` 解析
- 「那明天呢？」→ 继承 `last_places`，`travel_date=tomorrow`
- 「适合爸妈吗」「累不累」→ `key_concerns` + `single_place_suitability`
- 「会不会踩雷」→ `overrated_risk`；无上下文则澄清
- 可合理默认时不追问，写入 `assumptions`

**何时追问 vs 默认：**

- 无法解析「这里」且无 `last_places` → `needs_clarification=true`
- 有明确景点名或可从 catalog 识别 → 继续执行并记录 assumptions

### 为什么不是「用户问题 → 固定工具」？

用户常问的是**信息需求**（如“人流量怎么样”“适合推婴儿车吗”），而不是某个工具名。  
新链路先把自然语言转成 `TravelTask` + `InformationNeed`，再由 `ToolRouter` 按工具 **capabilities** 动态组合，例如：

| 用户问题 | 解析结果 | 工具组合 |
|---------|---------|---------|
| 这里人流量怎么样？（有上下文） | `crowd_inquiry` + `crowd_level` | `reviews` + `places` + `fallback` |
| 故宫今天人多吗？ | `crowd_inquiry` | 同上 + `weather` + `reservation_policy` |
| 适合带爸妈吗？ | `single_place_suitability` | `reviews` + `transit` + `official` + `restaurant` |

### Query Rewriter / Contextualizer

- 模块：`agents/query_rewriter.py`、`schemas/conversation_memory.py`
- 解析「这里、明天、刚才那个」等指代；补充模糊关注点（人多、累不累、踩雷）
- **不回答、不编造事实**；无法解析指代时 `needs_clarification=true`
- 通过 `user_context.conversation_memory.last_places` 传入上一轮景点

### TravelTask & InformationNeed

- `TravelTask`：任务类型、景点、关注点、所需证据字段
- `InformationNeed`：细粒度需求（`crowd_level`、`stroller_friendliness` 等）+ 优先级
- `InformationNeedPlanner` 根据任务生成需求列表

### Capability-based Tool Router

- `tools/capabilities.py` + `capability_registry.py` + `tool_router.py`
- 每个工具声明 capabilities（如 `reviews` → `crowd_level`）
- 无直接工具时走 `fallback`，并在 `limitations` 说明估算性质
- **人流量**：当前无 `live_crowd_tool`，使用评价 + 地图热门代理 + fallback，回答中明确「未接入实时人流」

## 架构要点（P2/P3）

- **Catalog 层**：`place_catalog` / `location_resolver` / `destination_catalog` 隔离 mock 数据与回答层
- **字段级 evidence**：`field_evidence_summary`（每字段 value + source_ids + confidence）
- **Claim/value 级引用检查**：`CitationChecker` 校验开放时间、票价、预约、天气等具体表述
- **多景点 per-place location**：`PlaceContext` 列表，compare 链路按景点独立 country/city 调工具
- **Review 两层管线**：规则抽取 + LLM structured extraction（默认关闭）
- **Tool 抽象**：`BaseTravelTool` + `TravelToolRegistry` + `ToolTrace`

## 功能范围

- 单景点情报卡、多景点比较、轻量行程
- `evidence_summary`（来源列表，兼容）+ `field_evidence_summary`（字段级，前端主用）
- `citation_check_result` / `tool_traces` / `conflicts` / `limitations`
- Golden + P0/P1 + P2/P3 + P4 架构评测

## 快速开始

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env
python -m compileall app
pytest app/evals -q
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### DeepSeek V4-Pro

```env
LLM_MODE=anthropic
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-v4-pro
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
```

离线演示可设 `LLM_MODE=mock`（不调用 LLM，evidence 链路仍完整）。

### API 示例

```bash
curl -X POST http://127.0.0.1:8000/api/travel/query ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"京都清水寺适合带父母去吗？\",\"user_context\":{\"party\":[\"elderly\"]}}"
```

## 目录结构

```text
backend/app/
  catalog/                  # PlaceCatalogService（回答层唯一地点入口）
  orchestrator/
    state_machine.py
    evidence_aggregator.py
    citation_check.py
  agents/
    conversation_context_builder.py
    query_understanding_agent.py
    rule_based_understanding.py
    query_rewriter.py          # 兼容包装
  orchestrator/
    states/query_understanding_state.py
    clarification_gate.py
  prompts/
    query_understanding.system.md
    query_understanding.user.md
    capability_registry.py
    tool_router.py          # need → tool routing
    fallback_tool.py
  schemas/
    place_factsheet.py      # FactValue + to_field_evidence_summary()
    place_context.py
  evals/
    p0_p1_tests.py
    p2_p3_tests.py
    p4_architecture_tests.py
    query_understanding_tests.py
```

## 如何新增景点 mock data

1. `tools/mock/data.py` → `PLACE_REGISTRY` / `PLACE_ALIASES` / `MOCK_REVIEWS`
2. `config.py` → `supported_cities`（如需要）
3. `agents/intent_agent.py` → RegionGate 关键词（如需要）
4. `evals/golden_queries.json` + 评测用例

Catalog 层通过 `MockPlaceCatalogBackend` 自动读取上述注册表，**无需**修改 Composer/Scorer。

## 如何替换真实 API

### 1. 实现 `BaseTravelTool`（返回 `list[Evidence]`）

```python
# backend/app/tools/real/weather_tool.py
class LiveWeatherTool(BaseTravelTool):
    name = "weather"
    async def run(self, city: str, country: str, **kwargs) -> list[Evidence]:
        ...
```

### 2. 在 `TravelToolRegistry` 中注册

```python
# backend/app/tools/registry.py
from app.tools.real.weather_tool import LiveWeatherTool
self.weather = LiveWeatherTool()  # 替换 MockWeatherTool
```

或通过 `use_mock=False` 分支加载 `app/tools/real/` 实现。

### 3. 配置密钥（`backend/.env`）

```env
WEATHER_API_KEY=...
MAPS_API_KEY=...
```

### 4. 验收

```bash
cd backend
python -m compileall app
pytest app/evals -q
```

**原则**：工具产 `Evidence` → Aggregator 产 `PlaceFactSheet`；Composer/Scorer 只读 FactSheet；不让 LLM 编造事实。

## 运行评测

```bash
cd backend
python -m compileall app
pytest app/evals -q
```

## 当前限制

- 重点支持 **日本、中国、韩国**；景点库覆盖有限
- 数据主要为 **mock**；评论合规需在真实接入时单独处理
- **CitationChecker** 为规则级 claim/value 检测，非完美事实验证
- **实时人流、实时排队、地图热力** 等需后续真实 API；当前为评价/代理估算
- LLM Review 抽取接口已预留，默认关闭
- 未接入 PostgreSQL / Redis / 生产前端

## 设计原则

- Evidence-first / Source-aware / Conflict-aware / Persona-aware
- State-machine constrained
- 无法证实的内容通过 `limitations` 或降低 `confidence` 表达

## 上传 GitHub

```powershell
.\upload_to_github.ps1 -DryRun
.\upload_to_github.ps1
```

详见 [RUNBOOK.md](RUNBOOK.md)。
