# MCP Setup Guide

Transport clients live in `packages/tools/mcp/client_manager.py`.  
**Do not** put GitHub repo URLs in `MCP_*_SERVER_URL` — only daemon base URLs.

## 先说清楚：两套「官方页」机制（不要混）

| 机制 | 开关 | 实际行为 |
|------|------|----------|
| **`official` 工具** | `ENABLE_REAL_OFFICIAL_PAGE` | **不是 MCP**。hybrid 下回退到 `PLACE_REGISTRY` mock；`true` 时走内置 URL 白名单 + httpx |
| **`official_page_reader_mcp`** | `MCP_SEARCH_*` + `OfficialPageFetchAdapter` | **已接通**：open-webSearch `POST /fetch-web` + 正文抽取 |
| **`browser_mcp`** | `MCP_BROWSER_*` + Playwright stdio | **已接通**：`browser_navigate` + `browser_snapshot` |
| **`search_mcp`** | `MCP_SEARCH_*` + open-webSearch | **已接通**：`POST /search` → Evidence |

`MCP_ENABLE_ALL=true` **不会**替代 `ENABLE_REAL_OFFICIAL_PAGE`。

## 实现状态

`packages/tools/mcp/adapter_status.py` 中的 `IMPLEMENTED_MCP_POLICIES` 是白名单唯一依据。

| Policy 工具 | 上游 | Adapter | 需 `MCP_PROFILE` |
|-------------|------|---------|------------------|
| `search_mcp` | open-webSearch `:3210` | `SearchMCPAdapter` | `search_only` 或 `full` |
| `official_page_reader_mcp` | `/fetch-web` | `OfficialPageFetchAdapter` | `search_only` 或 `full` |
| `browser_mcp` | Playwright stdio | `BrowserMCPAdapter` | `full` |
| `openmeteo_mcp` / `weather_mcp` / `climate_mcp` | Open-Meteo HTTP | `OpenMeteoMCPAdapter` | `full` |
| `osm_mcp` / `places_mcp` / `geocode_mcp` | OSM stdio | `OsmMCPAdapter` | `full` |
| `wikipedia_mcp` / `wikidata_mcp` | 各 stdio 包 | 专用 adapter | `full` |
| `sqlite_mcp` / `evidence_store_mcp` | mcp-sqlite | `SqliteMCPAdapter` | `full` |

验收脚本：

```powershell
.\scripts\verify-mcp-tools.ps1
```

## 推荐 `.env`

```env
TOOL_MODE=hybrid
ENABLE_REAL_OFFICIAL_PAGE=false

MCP_ENABLED=true
MCP_PROFILE=search_only           # 票价链路：search + official_page_reader
# MCP_PROFILE=full                # 全开已实现 MCP

MCP_SEARCH_TRANSPORT=open_websearch_http
MCP_SEARCH_SERVER_URL=http://127.0.0.1:3210

MCP_WIKIPEDIA_ARGS=-y,@cyanheads/wikipedia-mcp-server
MCP_OPENMETEO_TOOL_NAME=weather_forecast

MCP_HTTP_AUTOSTART=true
MCP_HTTP_AUTOSTART_KILL_STALE=true
MCP_BROWSER_TIMEOUT_SECONDS=45
```

改 `.env` 后 **重启 uvicorn**。

## Policy → 真实上游对照

见 `POLICY_TO_UPSTREAM` in `adapter_status.py`。

## E2E Manual Runbook

1. **中山陵票价** — `MCP_PROFILE=search_only`，启动 open-webSearch，查询「南京中山陵票价」；期望 `search_mcp` ≥1 Evidence，补充 `official_page_reader_mcp` 产出 `ticket_price` 或 limitation。
2. **清水寺开放时间** — `MCP_PROFILE=full` + Playwright；查询「清水寺今天几点关门」；期望 `official_page_reader_mcp` 或 `browser_mcp` 含 `opening_hours` claim。
3. **喀纳斯最佳月份** — `MCP_PROFILE=full`；查询「喀纳斯湖适合几月份去」；期望 `search_mcp` + 可选 `wikidata_mcp`/`climate_mcp` seasonality Evidence。

## 测试 mock

`MCP_SEARCH_SERVER_URL=mock://` + `register_mock_handler`（见 `mcp_evidence_planning_tests.py`）。
