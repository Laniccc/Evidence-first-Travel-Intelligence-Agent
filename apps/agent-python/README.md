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

### 示例（PowerShell，中文需 UTF-8）

Windows PowerShell 5.x 默认不是 UTF-8，直接 `-Body '...中文...'` 可能**发错编码**，终端也会把中文显示成乱码。先执行：

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

**推荐**用 UTF-8 字节发请求（请求与显示都正确）：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/agent/health

$json = '{"query":"京都清水寺适合带父母去吗？","session_id":"demo-session"}'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/agent/query `
  -ContentType "application/json; charset=utf-8" `
  -Body $bytes
```

或用 `curl.exe`（**`-d` 必须用单引号**，PowerShell 会改写双引号里的 `\"`）：

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/agent/query `
  -H "Content-Type: application/json; charset=utf-8" `
  -d '{"query":"京都清水寺适合带父母去吗？","session_id":"demo-session"}'
```

若仍报 `JSON decode error`，把 JSON 写入文件再发（最稳）：

```powershell
$path = Join-Path $env:TEMP "agent-query.json"
[System.IO.File]::WriteAllText(
  $path,
  '{"query":"京都清水寺适合带父母去吗？","session_id":"demo-session"}',
  [System.Text.UTF8Encoding]::new($false)
)
curl.exe -s -X POST http://127.0.0.1:8001/agent/query `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@$path"
```

若已安装 PowerShell 7（`pwsh`），可直接用其 `Invoke-RestMethod`，UTF-8 支持更好。

## 无 Maven 时的临时测试

本地没有 Java/Maven 时，**只启动本服务**即可验证 Agent 核心：

1. 按上文启动 agent-python（8001）
2. 浏览器打开 `http://127.0.0.1:8001/agent/health`
3. 用上面 `Invoke-RestMethod` 或 `curl` 调 `/agent/query`

若要 **网页界面** 且暂时没有 api-java，见 [`apps/web/README.md` — 临时绕过 api-java](../web/README.md#临时绕过-api-java无-maven)（改 Vite 代理后 `npm run dev`）。

完整三件套（含 Java Gateway）需安装 Maven 后在 `apps/api-java` 执行 `mvn spring-boot:run`。

## Java Tool Gateway（可选）

| 变量 | 默认 | 说明 |
|------|------|------|
| `USE_JAVA_TOOL_GATEWAY` | `false` | 是否启用 Java 转发 |
| `TOOL_GATEWAY_BASE_URL` | `http://localhost:8082` | 需 api-java 已启动 |

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
