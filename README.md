# Evidence-first Travel Intelligence Agent

面向日本、中国、韩国的 **Evidence-first Travel Intelligence Agent**。

> **当前状态：Mock MVP**  
> 景点开放时间、票价、交通、天气、评价等均来自 `backend/app/tools/mock_data.py` 的结构化 mock 工具，经 `Evidence` → `PlaceFactSheet` 聚合后，再由评分器与 Composer 生成回答。  
> **不会**在缺少证据时编造关键事实；接入真实 API 前请勿将输出当作真实票务/开放信息。

**运维手册**：[RUNBOOK.md](RUNBOOK.md)

## 架构要点（P0/P1）

```text
用户查询
  → Region Gate / Intent / Context（含景点城市回填）
  → SourceSelectionPolicy（按意图选择工具）
  → Tools → Evidence[]
  → EvidenceAggregator → PlaceFactSheet（统一事实表）
  → ReviewAspectMining → ReviewAspectResult
  → TravelSuitabilityScorer（仅读 FactSheet + Review + UserGoal）
  → ComposerAgent（仅读 FactSheet + Review + Recommendation）
  → CitationChecker（无证据支撑则降置信度 + limitations）
```

`TravelSuitabilityScorer` 与 `ComposerAgent` **不直接读取** `PLACE_REGISTRY`。

## 功能范围（Mock MVP）

- 单景点情报卡
- 多景点比较
- 轻量一日/半日行程（仅使用已注册景点）
- `visible_trace` / `evidence_summary` / `conflicts` / `limitations`
- Golden + P0/P1 评测

## 快速开始

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### DeepSeek V4-Pro（与 ClaudeAgent_A 相同方式）

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
  orchestrator/
    state_machine.py       # S0–S12 状态链
    evidence_aggregator.py   # Evidence → PlaceFactSheet
    citation_check.py        # 引用与限制检查
    policies.py              # SourcePriority + SourceSelection
  agents/
    place_research_agent.py  # 按策略调用 tools
    suitability_scorer.py
    composer_agent.py
  tools/mock_data.py         # Mock 景点库（仅 tools 层使用）
  schemas/place_factsheet.py
  evals/
    golden_queries.json
    p0_p1_tests.py
```

## 如何替换真实 API

### 1. 新建 Tool（必须返回 `Evidence`）

```python
# backend/app/tools/weather_tool_live.py
class LiveWeatherTool(BaseTool):
    name = "weather"
    async def run(self, city: str, country: str, travel_date: str | None = None, **kwargs) -> list[Evidence]:
        # 调用真实天气 API
        return [Evidence(source_type=SourceType.WEATHER_API, claims=[...], ...)]
```

### 2. 在 `ToolRegistry` 中替换 mock

```python
# backend/app/tools/__init__.py
self.weather = LiveWeatherTool()  # 替换 MockWeatherTool
```

### 3. 配置密钥（`backend/.env`）

```env
WEATHER_API_KEY=...
MAPS_API_KEY=...
DEEPSEEK_API_KEY=...
```

### 4. 扩展 `config.py` 读取新密钥

### 5. 验收

```bash
cd backend
python -m compileall app
pytest app/evals -q
```

**原则**：

- 工具产 `Evidence`，Aggregator 产 `PlaceFactSheet`
- Composer / Scorer 只消费 FactSheet，不读 registry、不让 LLM 编造开放时间/票价
- 评论数据遵守平台条款，仅存摘要与 aspect

## 新增景点（mock 阶段）

1. `tools/mock_data.py` → `PLACE_REGISTRY` / `PLACE_ALIASES` / `MOCK_REVIEWS`
2. `config.py` → `supported_cities`
3. `agents/intent_agent.py` → 识别关键词
4. `evals/golden_queries.json` + `p0_p1_tests.py` 补充用例

## 运行评测

```bash
cd backend
pytest app/evals -q
```

包含：`test_compile_imports`、`test_weather_called_when_city_backfilled`、`test_conflict_resolution_prefers_official` 等 P0/P1 用例。

## 设计原则

- Evidence-first / Source-aware / Conflict-aware / Persona-aware
- State-machine constrained
- East Asia first（日本 / 中国 / 韩国）

## 已知限制（Mock MVP）

- 景点库覆盖有限（`PLACE_REGISTRY`）
- 天气/交通/评论为 mock 或摘要级
- 未接入 PostgreSQL / Redis / 前端
- LLM 辅助 intent 解析；核心事实来自 tools

## 上传 GitHub

```powershell
.\upload_to_github.ps1 -DryRun
.\upload_to_github.ps1
```

详见 [RUNBOOK.md §12](RUNBOOK.md#12-上传项目到-github)。
