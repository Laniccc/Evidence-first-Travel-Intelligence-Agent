# apps/agent-python — Travel Agent 独立入口

Python Agent 核心服务的 **独立 FastAPI 进程**。对外仅暴露 `/agent/*`；内部临时复用 `backend/app` 中的状态机（legacy，只读）。

## 前置条件

- Python 3.11+
- 依赖：与 legacy `backend` 相同（推荐直接安装 backend 的 requirements）

```powershell
cd apps/agent-python
pip install -r requirements.txt
pip install -r ../../backend/requirements.txt
```

- 环境变量：使用 `backend/.env`（从 `backend/.env.example` 复制）。在 `backend` 目录或本目录设置均可；`app.config` 从 legacy backend 加载。

```powershell
# 可选：指向 backend 的 .env
$env:DOTENV_PATH = "..\..\backend\.env"
```

## 启动

```powershell
cd apps/agent-python
python -m compileall app

# 推荐使用 backend 虚拟环境（已安装全部依赖）
..\..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

> 默认使用 **8001**，避免与 legacy `backend`（8000）冲突。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/agent/health` | 健康检查 |
| POST | `/agent/query` | 旅行问答（契约见 `contracts/schemas/travel_query_*.schema.json`） |

### 示例

```powershell
curl http://127.0.0.1:8001/agent/health

curl -X POST http://127.0.0.1:8001/agent/query `
  -H "Content-Type: application/json" `
  -d "{\"query\":\"京都清水寺适合带父母去吗？\",\"session_id\":\"demo-session\"}"
```

响应最小字段：`answer`、`session_id`、`query_id`、`visible_trace`、`evidence_summary`、`limitations`、`confidence`、`tool_traces`。

## Java Tool Gateway（可选）

当 `USE_JAVA_TOOL_GATEWAY=true` 时，MCP 类工具（名称以 `_mcp` 结尾或命中 MCP policy）在 `ActionExecutor._call_tool` 中会 **先转发** 到 Java API 的 `POST /internal/tools/call`，再按响应写回 `Evidence` 与 `tool_traces`。失败时写入 `limitations` 并 **回退** 到本地 `tools.run_tool`，不崩溃。

| 变量 | 默认 | 说明 |
|------|------|------|
| `USE_JAVA_TOOL_GATEWAY` | `false` | 是否启用 Java 转发 |
| `TOOL_GATEWAY_BASE_URL` | `http://localhost:8080` | Java `apps/api-java` 基址 |

```powershell
# 需同时启动 api-java（8080）与 agent-python（8001）
$env:USE_JAVA_TOOL_GATEWAY = "true"
$env:TOOL_GATEWAY_BASE_URL = "http://127.0.0.1:8080"
..\..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

实现位置：`app/tool_gateway/`（`java_client.py`、`integration.py`）。默认 `false` 时行为与 legacy 完全一致。

## S5 白名单与 Tool Gateway

S5（`app/orchestrator/states/evidence_planning_and_tool_use_state.py`）通过 `ToolWhitelistBuilder` 生成 **任务级动态白名单**，prompt 中仅暴露 `allowed_tools`（不含静态 router 目录）。

- `PolicyGuard` / `EvidencePolicyGuard`：校验状态级 + 动态白名单；`knowledge_prior` 禁止用于 `opening_hours` / `ticket_price` / `today_weather` / `current_crowd` 等强事实需求
- `CALL_TOOL` 经 `ActionExecutor` 执行；`USE_JAVA_TOOL_GATEWAY=true` 时 MCP 工具走 Java `POST /internal/tools/call`
- `ToolTrace` 字段：`requested_by_state=S5`、`selected_by_llm`、`whitelist_checked`
- `MODEL_PRIOR_ALLOWED` 经 `_run_advisory` 进入 S5，由工具队列决定先尝试 search/climate/entity，而非直接 KnowledgePrior

验收测试（需 backend 依赖与虚拟环境）：

```powershell
cd apps/agent-python
..\..\backend\.venv\Scripts\python.exe -m pytest tests/test_s5_whitelist.py -v
```

## 说明

- **无前端页面**，不提供 static 挂载。
- **无服务端长期 session**；仅消费请求中的 `user_context`（及可选 `session_id` 回显）。
- 契约模型见 `app/contract.py`；比 legacy 响应更窄，但兼容 `contracts/schemas/`。
- 新功能应写在本目录，勿再写入 `backend/`（见 `backend/LEGACY.md`）。
