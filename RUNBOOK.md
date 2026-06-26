# Runbook

端口：MCP 搜索 `3210` | Agent `8001` | api-java `8082` | web `5173`

依赖：Python 3.11+、Node 18+（MCP/web）、Java 17+（api-java 可选）

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

**默认**：Agent 进入 S5 时会检测 HTTP MCP 是否健康；不健康时若端口被僵死进程占用会先 `taskkill` 再新开终端拉起。

仓库根目录 — 启动 MCP 网页搜索（:3210，单独终端保持运行）

```powershell
.\scripts\start-mcp-stack.ps1
curl http://127.0.0.1:3210/health
# 验证搜索（默认 baidu 引擎，国内可用）
curl -X POST http://127.0.0.1:3210/search -H "Content-Type: application/json" -d "{\"query\":\"独库公路 开放\",\"limit\":2,\"engines\":[\"baidu\"]}"
```

可选天气 MCP（:3000）：

```powershell
.\scripts\start-mcp-stack.ps1 -IncludeWeather
```

仅检查 MCP 是否在跑：

```powershell
.\scripts\start-mcp-stack.ps1 -StatusOnly
```

browser/osm 等 stdio MCP 无需单独启动，Agent 调用时自动 npx。

## 仅 Agent

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
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

改 `.env` 后需重启 uvicorn。

## 四件套（web 页面）

终端 0 — MCP 搜索（仓库根目录，单独窗口保持运行；**建议在 Agent 之前启动**）：

```powershell
cd "E:\学习文件\研究生\就业\Agent学习\Evidence-first Travel Intelligence Agent"
.\scripts\start-mcp-stack.ps1
curl http://127.0.0.1:3210/health
```

终端 1 Agent：

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

终端 2 api-java：

```powershell
cd apps/api-java
mvn spring-boot:run
```

终端 3 web：

```powershell
cd apps/web
npm install
npm run dev

cd apps/web
npm run dev
```

浏览器 http://127.0.0.1:5173

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
| 找不到 app 模块 | `cd apps/agent-python`，`$env:PYTHONPATH=(Get-Location).Path` |
| search_mcp 失败 | `.\scripts\start-mcp-stack.ps1`，`curl http://127.0.0.1:3210/health` |
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
| 页面「请求失败」/ 无回答 | 检索类问题可等 1–3 分钟；确认 api-java :8082（`agent.read-timeout` 默认 300s）与 web `VITE_QUERY_TIMEOUT_MS=300000`；勿用旧版 8080/120s 配置 |
| 改配置不生效 | 重启 uvicorn / 重启 api-java / 重启 `npm run dev` |

MCP 细节见 [docs/mcp-setup.md](docs/mcp-setup.md)

## 上传 GitHub

```powershell
.\upload_to_github.ps1 -Message "your message"
```

勿提交 `apps/agent-python/.env`
