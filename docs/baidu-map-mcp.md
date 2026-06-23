# Baidu Map MCP (P0–P4)

Baidu Map MCP provides LBS capabilities for the travel agent: POI search, geocoding, routing, traffic, and short-term weather.

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

When `MCP_BAIDU_MAP_ENABLED=false` or `BAIDU_MAP_AK` is empty, no `baidu_*` tools are registered or whitelisted.

## Policy tools (P0–P4)

| Tool | Upstream | Phase | Use |
|------|----------|-------|-----|
| `baidu_place_search_mcp` | `map_search_places` | P0 | Place lookup / disambiguation |
| `baidu_place_detail_mcp` | `map_place_details` | P0 | POI details (candidate hours/price) |
| `baidu_weather_mcp` | `map_weather` | P0 | Short-term weather only |
| `baidu_geocode_mcp` | `map_geocode` | P1 | Address → coordinates |
| `baidu_reverse_geocode_mcp` | `map_reverse_geocode` | P1 | Coordinates → address / admin area |
| `baidu_route_mcp` | `map_directions` | P2 | Driving / walking / transit routes |
| `baidu_route_matrix_mcp` | `map_directions_matrix` | P2 | Multi-point distance/time matrix |
| `baidu_traffic_mcp` | `map_road_traffic` | P3 | Road traffic / congestion |
| `baidu_ip_location_mcp` | `map_ip_location` | P4 | User city estimate (privacy-gated) |

## S5 call order (China)

When a place exists but city/region/coordinates are missing:

1. `baidu_place_search_mcp`
2. `baidu_place_detail_mcp` (if uid available)
3. `baidu_geocode_mcp` or `baidu_reverse_geocode_mcp`
4. Then `openmeteo_mcp` / `climate_mcp` / `baidu_weather_mcp` / route / traffic tools

Coordinates from Baidu evidence are injected into weather tools before Open-Meteo calls.

## Evidence boundaries (LBS vs official)

- `price_candidate` / `opening_hours_candidate` are **not** official `ticket_price` / `opening_hours`.
- Ticket price and official hours still prefer `search_mcp` + `official_page_reader_mcp` / `browser_mcp`.
- `baidu_weather_mcp` is for near-term trips; long-term “best month” uses `search_mcp`, `climate_mcp`, `seasonality`, or `knowledge_prior`.
- Route/traffic results are map-engine estimates; road closures and scenic regulations need official/search evidence.
- Baidu MCP JSON is normalized to `Evidence[]` with `ClaimType` — never passed raw to the composer.

## IP location privacy

`baidu_ip_location_mcp` is allowed only when:

- Request `user_context.location_usage_allowed=true`, or
- User query explicitly mentions nearby-me intent (e.g. 我附近 / 从我这里 / 附近有什么)

Otherwise the tool is blocked in the whitelist and rejected by `EvidencePolicyGuard`. Tool traces mark `input.location_sensitive=true` for IP calls.

## AK application

Apply for a server-side AK at [百度地图开放平台](https://lbsyun.baidu.com/).

See also: [mcp-setup.md](mcp-setup.md)
