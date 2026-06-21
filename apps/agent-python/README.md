# apps/agent-python — Travel Agent 独立入口

Python Agent 核心服务的 **独立 FastAPI 进程**。运行时不再依赖 `backend/`；工具实现以 [`packages/tools`](../../packages/tools/) 为真相源，`app/tools/` 为薄 shim。

## 前置条件

- Python 3.11+
- 依赖：

```powershell
cd apps/agent-python
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

## 启动

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m compileall app
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

> 默认 **8001**，与旧 `backend`（8000，只读存档）错开端口。

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

## Java Tool Gateway（可选）

| 变量 | 默认 | 说明 |
|------|------|------|
| `USE_JAVA_TOOL_GATEWAY` | `false` | 是否启用 Java 转发 |
| `TOOL_GATEWAY_BASE_URL` | `http://localhost:8080` | Java `apps/api-java` 基址 |

## 架构

```
apps/agent-python/app/     orchestrator, agents, schemas, config
packages/tools/            工具注册与 MCP（canonical）
app/tools/                 指向 packages/tools 的 shim
app/tool_gateway/          Java Tool Gateway 客户端
```

## 测试

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/test_s5_whitelist.py -v
```

## 说明

- **无前端页面**；Web 经 `apps/api-java` 调用本服务。
- `backend/` 仅作只读对照与紧急回退参考，见 [`backend/LEGACY.md`](../../backend/LEGACY.md)。
