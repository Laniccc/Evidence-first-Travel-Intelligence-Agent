# apps/agent-python — Travel Agent 独立入口

Python Agent 核心服务的 **独立 FastAPI 进程**。工具实现以 [`packages/tools`](../../packages/tools/) 为真相源，`app/tools/` 为薄 shim。

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

`.env` 必须配置 `DEEPSEEK_API_KEY`（或 `ANTHROPIC_API_KEY`），并设 `LLM_MODE=anthropic`。本项目不支持离线/模拟 LLM 模式，需联网运行。

## 启动

推荐从仓库根目录启动，脚本会自动设置 `PYTHONPATH`、执行轻量 compile 检查，并按需启动 MCP 搜索栈：

```powershell
conda activate ClaudeAgent
# 回到仓库根目录后执行
.\scripts\start-agent.ps1
```

常用参数：

```powershell
.\scripts\start-agent.ps1 -NoMcp
.\scripts\start-agent.ps1 -AllowMcpFailure
.\scripts\start-agent.ps1 -Port 8002
.\scripts\start-agent.ps1 -NoReload -SkipCompileCheck
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

1. 在仓库根目录执行 `.\scripts\start-agent.ps1`
2. 浏览器打开 `http://127.0.0.1:8001/agent/health`
3. 用上面 `Invoke-RestMethod` 或 `curl` 调 `/agent/query`

若要 **网页界面**，仓库根目录执行 `.\scripts\start-agent.ps1` 会默认启动 Web 并直连 agent-python；完整 Gateway 链路见 [`apps/web/README.md`](../web/README.md)。

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

- **无内置前端页面**；本地 Web 默认链路为 `web → agent-python`，完整 Gateway 链路为 `web → api-java → agent-python`。
- 调试日志：每次 `/agent/query` 后写入 `debug_last_session.md`（覆盖）。
