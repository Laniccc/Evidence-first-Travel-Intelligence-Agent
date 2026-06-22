# Baidu Map MCP

Baidu Map MCP provides LBS capabilities for the travel agent: POI search, place details, and short-term weather.

## Official endpoints

- Streamable HTTP (recommended): `https://mcp.map.baidu.com/mcp?ak=YOUR_AK`
- SSE (backup): `https://mcp.map.baidu.com/sse?ak=YOUR_AK`

## Local stdio (optional)

```bash
npx -y @baidumap/mcp-server-baidu-map
```

Set `BAIDU_MAP_API_KEY` in the subprocess environment (handled automatically when `MCP_BAIDU_MAP_STDIO_ENABLED=true`).

## Configuration

Add to `apps/agent-python/.env` (never commit AK):

```env
BAIDU_MAP_AK=your_server_ak
MCP_BAIDU_MAP_ENABLED=true
MCP_BAIDU_MAP_TRANSPORT=baidu_streamable_http
MCP_BAIDU_MAP_SERVER_URL=https://mcp.map.baidu.com/mcp
```

Baidu MCP is **independent** of `MCP_PROFILE=search_only`. It only requires:

- `MCP_ENABLED=true`
- `MCP_BAIDU_MAP_ENABLED=true`
- non-empty `BAIDU_MAP_AK`

## Policy tools

| Tool | Upstream | Use |
|------|----------|-----|
| `baidu_place_search_mcp` | `map_search_places` | Place lookup / disambiguation |
| `baidu_place_detail_mcp` | `map_place_details` | POI details (candidate hours/price) |
| `baidu_weather_mcp` | `map_weather` | Short-term weather only |

## Evidence boundaries

- `price_candidate` / `opening_hours_candidate` are **not** official ticket_price / opening_hours.
- Ticket price and official hours still prefer `search_mcp` + `official_page_reader_mcp` / `browser_mcp`.
- `baidu_weather_mcp` is for near-term trips; long-term “best month” still uses `search_mcp`, `climate_mcp`, `seasonality`, or `knowledge_prior`.

## AK application

Apply for a server-side AK at [百度地图开放平台](https://lbsyun.baidu.com/).

See also: [mcp-setup.md](mcp-setup.md)
