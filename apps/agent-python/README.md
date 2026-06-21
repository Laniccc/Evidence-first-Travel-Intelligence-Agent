# apps/agent-python — Travel Agent 独立入口

Python Agent 核心服务的 **独立 FastAPI 进程**。运行时不再依赖 `backend/`；工具实现以 [`packages/tools`](../../packages/tools/) 为真相源，`app/tools/` 为薄 shim。

## 前置条件

- Python 3.11+（推荐 Conda 环境，如 `ClaudeAgent`）
- 依赖：

```powershell
conda activate ClaudeAgent
cd apps/agent-python
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

`.env` 建议先设 `LLM_MODE=mock`（无 API Key 也能跑通）；有 DeepSeek Key 再改 `LLM_MODE=anthropic` 并填写 `DEEPSEEK_API_KEY`。

## 启动

```powershell
conda activate ClaudeAgent
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m compileall app
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

> 默认 **8001**。根路径 `/` 无页面，请用 `/agent/health`。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/agent/health` | 健康检查 |
| POST | `/agent/query` | 旅行问答 |

### 示例（PowerShell）

```powershell
Invoke-RestMethod http://127.0.0.1:8001/agent/health

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/agent/query `
  -ContentType "application/json" `
  -Body '{"query":"京都清水寺适合带父母去吗？","session_id":"demo-session"}'
```

## 无 Maven 时的临时测试

本地没有 Java/Maven 时，**只启动本服务**即可验证 Agent 核心：

1. 按上文启动 agent-python（8001）
2. 浏览器打开 `http://127.0.0.1:8001/agent/health`
3. 用上面 `Invoke-RestMethod` 调 `/agent/query`

若还要 **网页界面** 且暂时没有 api-java，可在 `apps/web/vite.config.js` 里临时把代理指到 Agent（测完改回）：

```javascript
proxy: {
  "/api": {
    target: "http://localhost:8001",
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api\/travel\/query/, "/agent/query"),
  },
},
```

然后 `cd apps/web && npm run dev`，打开 http://127.0.0.1:5173 。此时跳过 Java 层，无 session 记忆。

完整三件套（含 Java Gateway）需安装 Maven 后在 `apps/api-java` 执行 `mvn spring-boot:run`。

## Java Tool Gateway（可选）

| 变量 | 默认 | 说明 |
|------|------|------|
| `USE_JAVA_TOOL_GATEWAY` | `false` | 是否启用 Java 转发 |
| `TOOL_GATEWAY_BASE_URL` | `http://localhost:8080` | 需 api-java 已启动 |

## 测试

```powershell
conda activate ClaudeAgent
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/test_s5_whitelist.py -v
```

## 说明

- **无前端页面**；正常链路为 `web → api-java → agent-python`。
- `backend/` 仅只读对照，见 [`backend/LEGACY.md`](../../backend/LEGACY.md)。
