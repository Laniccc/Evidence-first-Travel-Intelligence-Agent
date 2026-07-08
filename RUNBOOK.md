# Runbook

端口：MCP 搜索 `3210` | Agent `8001` | api-java `8082` | web `5173`

依赖：Python 3.11+、Node 18+（MCP/web）、Java 17+（api-java 可选）

## 常用地址

| 服务 | 地址 | 说明 |
|------|------|------|
| Web 界面 | http://127.0.0.1:5173/ | 由 `.\scripts\start-agent.ps1` 默认启动 |
| Agent 健康检查 | http://127.0.0.1:8001/agent/health | `.\scripts\start-agent.ps1` 启动 |
| Agent 问答 API | POST http://127.0.0.1:8001/agent/query | 只接受 POST，浏览器直接打开会返回 405 |
| MCP 搜索健康检查 | http://127.0.0.1:3210/health | 由 `start-agent.ps1` 自动检查/启动 |
| Java Gateway | http://127.0.0.1:8082/ | 可选，需在 `apps/api-java` 单独启动 |

本地 Web 默认直连 `agent-python :8001`；需要完整 Java Gateway 链路时，用 `.\scripts\start-agent.ps1 -WebViaGateway` 并单独启动 `api-java :8082`。

## 首次安装

```powershell
cd apps/agent-python
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`：填 `DEEPSEEK_API_KEY`，保留 `MCP_ENABLE_ALL=true`。

```powershell
node -v
npx -v
```

npx 报 EPERM 时：

```powershell
$env:npm_config_cache = "$env:USERPROFILE\.npm-cache"
```

## 启动顺序

默认从仓库根目录一条命令启动 Agent + MCP 搜索栈 + Web：

```powershell
.\scripts\start-agent.ps1
```

脚本会自动完成：

1. 若 `apps/agent-python/.env` 不存在，则从 `.env.example` 复制；
2. 检查/启动 HTTP MCP 网页搜索栈（:3210）；
3. 检查/启动 Web dev server（:5173），首次缺 `node_modules` 时自动 `npm install`；
4. 进入 `apps/agent-python` 并设置 `PYTHONPATH`；
5. 运行 `python -m compileall app -q` 做轻量启动前检查；
6. 启动 uvicorn Agent（默认 :8001，开启 reload）。

常用参数：

```powershell
# 只启动 Agent，不拉起 MCP（适合 MCP 已在跑或离线调试）
.\scripts\start-agent.ps1 -NoMcp

# 不启动 Web
.\scripts\start-agent.ps1 -NoWeb

# 只启动 Web（适合后端已在运行时补开页面）
.\scripts\start-agent.ps1 -WebOnly

# Web 走 Java Gateway（需单独启动 api-java :8082）
.\scripts\start-agent.ps1 -WebViaGateway

# Web 启动失败仍继续启动 Agent
.\scripts\start-agent.ps1 -AllowWebFailure

# MCP 启动失败仍继续启动 Agent（检索证据会不完整）
.\scripts\start-agent.ps1 -AllowMcpFailure

# 同时拉起可选天气 MCP
.\scripts\start-agent.ps1 -IncludeWeatherMcp

# 换端口
.\scripts\start-agent.ps1 -Port 8002

# 生产式本地运行：关闭 reload，跳过 compileall
.\scripts\start-agent.ps1 -NoReload -SkipCompileCheck
```

健康检查：

```powershell
curl http://127.0.0.1:8001/agent/health
```

### MCP 单独管理（可选）

正常启动无需手动运行 MCP；`start-agent.ps1` 会调用 `start-mcp-stack.ps1`。需要单独检查或调试 MCP 时使用：

```powershell
.\scripts\start-mcp-stack.ps1 -StatusOnly
.\scripts\start-mcp-stack.ps1
.\scripts\start-mcp-stack.ps1 -KillStalePort
curl http://127.0.0.1:3210/health
```

MCP 启动日志在 `logs/mcp/open-websearch.out.log` 和 `logs/mcp/open-websearch.err.log`。首次运行需要 `npx` 下载 `open-websearch@latest`，若 npm 源或代理不可用，会在这里看到真实错误。

验证搜索（默认 baidu 引擎，国内可用）：

```powershell
curl -X POST http://127.0.0.1:3210/search -H "Content-Type: application/json" -d "{\"query\":\"独库公路 开放\",\"limit\":2,\"engines\":[\"baidu\"]}"
```

browser/osm 等 stdio MCP 无需单独启动，Agent 调用时自动 npx。

## 仅 Agent

```powershell
.\scripts\start-agent.ps1 -NoMcp -NoWeb
```

```powershell
curl http://127.0.0.1:8001/agent/health
```

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/agent/query `
  -H "Content-Type: application/json; charset=utf-8" `
  -d '{"query":"京都清水寺适合带父母去吗？","session_id":"demo"}'
```

调试日志：`apps/agent-python/debug_last_session.md`

改 `.env` 后需重启 Agent。

### Agent Core Store

默认：

```env
AGENT_CORE_STORE_BACKEND=memory
```

需要审计/复盘时：

```env
AGENT_CORE_STORE_BACKEND=jsonl
AGENT_CORE_STORE_JSONL_PATH=./data/agent_core_store.jsonl
```

需要 SQL 查询事件时：

```env
AGENT_CORE_STORE_BACKEND=sqlite
AGENT_CORE_STORE_SQLITE_PATH=./data/agent_core_store.sqlite3
```

SQLite 会写入 `agent_core_events(run_id, event_type, payload_json, created_at)`；调试优先看 `debug_last_session.md` 的 `Agent Core Projection`。

## Web 页面

默认启动命令已经包含 Web：

```powershell
.\scripts\start-agent.ps1
```

如果 Agent 已经在运行，只补开 Web：

```powershell
.\scripts\start-agent.ps1 -WebOnly
```

浏览器打开 Web 界面：http://127.0.0.1:5173/

Web 启动日志：`logs/web/vite.out.log` / `logs/web/vite.err.log`

## 四件套（完整链路）

终端 1 — Agent + MCP + Web（仓库根目录）：

```powershell
.\scripts\start-agent.ps1
```

终端 2 — api-java：

```powershell
cd apps/api-java
mvn spring-boot:run
```

如果 MCP 已经在别的窗口单独运行，Agent + Web 也可以用：

```powershell
.\scripts\start-agent.ps1 -NoMcp
```

链路：web :5173 → api-java :8082 → agent :8001；agent S5 依赖 open-webSearch :3210

## 评测

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
pytest app/evals -q
```

## 故障

| 现象 | 命令/处理 |
|------|-----------|
| 找不到 app 模块 | 优先从仓库根目录运行 `.\scripts\start-agent.ps1`；脚本会自动设置 `PYTHONPATH` |
| search_mcp 失败 | 默认运行 `.\scripts\start-agent.ps1`；单独排查用 `.\scripts\start-mcp-stack.ps1 -StatusOnly` 和 `curl http://127.0.0.1:3210/health`；看 `logs/mcp/open-websearch.err.log` |
| baidu 搜索 302 / 全空 | `.env` 设 `MCP_SEARCH_USE_PROXY=true` 并重启 open-webSearch；或 `MCP_SEARCH_DEFAULT_ENGINE=sogou`；client 会自动回退 `MCP_SEARCH_FALLBACK_ENGINES` |
| 携程/点评 0 命中 / 垃圾 URL | 默认已关：`CTRIP_CRAWLER_ENABLED=false`、`DIANPING_CRAWLER_ENABLED=false`、`*_WEBSEARCH_SIGNAL_ENABLED=false`；S5 显示 `disabled_by_config` 为预期；nearby 美食走 `baidu_place_search` |
| subprocess 爬虫联调 | 先 `.\scripts\crawlers\install-deps.ps1`；验证通过后再把对应 `*_CRAWLER_ENABLED=true` 打开 |
| guide/nearby/crowd 新工具 | `ENABLE_TRAVEL_NOTE_CRAWLERS` + `--mode guide`；`ENABLE_NEARBY_PLATFORM_CRAWLERS` + `dianping_cli --mode nearby`；`ENABLE_CROWD_ESTIMATION_TOOLS=true` + smoke `check_crowd_estimation.py` |
| :3210 已被占用 | 服务已在跑，勿重复启动 |
| npx EPERM | `$env:npm_config_cache="$env:USERPROFILE\.npm-cache"` |
| 无证据/回答差 | 看 `debug_last_session.md` |
| S7 gap 回环未补证 | 查 trace 中 `S5 gap-filling`；默认 `EVIDENCE_MAX_GAP_ROUNDS=1`；重复 `gap_signature` 会跳过 |
| ticket_price 只有平台价、无官方确认 | 查 trace 中 `official_source_discovery` / `urls_checked_count`；看 gap request 是否含 `official_source_discovery_mcp`；见 [docs/official-source-discovery.md](docs/official-source-discovery.md) |
| ticket_price 多数字冲突、回答称「不确定」 | 查 trace 是否触发 `evidence_contradiction_decomposer_agent`；看 `structured_result.fact_decomposition` 是否按票种分拆 |
| Web 提交后显示 Internal Server Error | 查 `logs/web/vite.err.log`；若有 `http proxy error` / `ECONNREFUSED :8082`，说明 Web 走了未启动的 Java Gateway，重启 `.\scripts\start-agent.ps1 -WebOnly` 使用本地 direct agent，或启动 `api-java :8082` |
| 页面「请求失败」/ 无回答 | 检索类问题可等 1–3 分钟；本地 direct 模式确认 agent-python :8001；Gateway 模式确认 api-java :8082（`agent.read-timeout` 默认 300s）与 web `VITE_QUERY_TIMEOUT_MS=300000`；勿用旧版 8080/120s 配置 |
| `GET /agent/query` 返回 405 | 正常现象；`/agent/query` 只接受 `POST`，浏览器健康检查请访问 `/agent/health` |
| 改配置不生效 | 重启 `.\scripts\start-agent.ps1` / 重启 api-java / 重启 `npm run dev` |

MCP 细节见 [docs/mcp-setup.md](docs/mcp-setup.md)

## 上传 GitHub

```powershell
.\upload_to_github.ps1 -Message "your message"
```

勿提交 `apps/agent-python/.env`
