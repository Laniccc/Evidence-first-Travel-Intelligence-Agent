# S5 Information Domains

Evidence-first Travel Intelligence Agent organizes S5 tool acquisition in three layers:

```
Information Domain → Provider Group → Concrete MCP Tool
```

This document describes the framework skeleton. Platform crawlers (Ctrip, Dianping, Xiaohongshu, etc.) are **placeholders only** — registered for planning and trace, not implemented in this round.

## Architecture

1. **Information Domain** — what kind of information the agent needs (geo, tickets, seasonality, …).
2. **Provider Group** — which class of provider supplies that information (Baidu LBS, search, ticket platform, …).
3. **Concrete MCP Tool** — the actual policy-level tool name invoked in S5 (`search_mcp`, `baidu_route_mcp`, `ctrip_ticket_crawler_mcp`, …).

Flow:

- `ResponseContract` + `SemanticFrame` → `S5DomainPlanner` → `S5DomainPlan`
- `ToolWhitelistBuilder` merges domain bindings with contract `preferred_tools`
- `EvidencePolicyGuard` / `EvidenceCoverageChecker` enforce domain semantics

## Eight Information Domains

### geo_resolution

**Role:** Resolve place names, POI, coordinates, administrative areas.

**Provider:** `baidu_lbs_provider` (primary), `search_provider` / OSM (fallback)

**Tools:** `baidu_place_search_mcp`, `baidu_place_detail_mcp`, `baidu_geocode_mcp`, `baidu_reverse_geocode_mcp`, `osm_mcp`, `wikidata_mcp`, `wikipedia_mcp`, `search_mcp`

**Claim types:** `entity_resolution`, `place_lookup`, `coordinates`, `administrative_area`, `disambiguation`

Often a **prerequisite** when city/coordinates are missing.

### ticket_booking

**Role:** Ticket price, types, discounts, reservation and booking channels.

**Provider:** `official_web_provider`, `search_provider`, `ticket_platform_provider` (placeholders)

**Tools:** `official_page_reader_mcp`, `search_mcp`, `browser_mcp`, `baidu_place_detail_mcp` (candidate); platform placeholders (`ctrip_*`, `fliggy_*`, …)

**Forbidden:** `knowledge_prior` for hard-fact ticket claims

### operation_status

**Role:** Opening hours, closures, seasonal road/scenic operation, capacity notices.

**Provider:** `official_web_provider`, `baidu_lbs_provider`, `crawler_provider` (placeholders)

**Tools:** `official_page_reader_mcp`, `search_mcp`, `browser_mcp`, `baidu_place_detail_mcp`, `tourism_board_notice_mcp` (placeholder)

**Forbidden:** `knowledge_prior` for required hard-fact operation claims

### seasonality

**Role:** Best time to visit, monthly weather/scenery, seasonal crowd patterns.

**Provider:** `baidu_lbs_provider`, `weather_provider`, `search_provider`, `model_prior_provider` (fallback)

**Tools:** Baidu geo, `openmeteo_mcp`, `climate_mcp`, `seasonality`, `search_mcp`; note crawlers are placeholders (`mafengwo_*`, `xiaohongshu_*`, `ctrip_guide_*`)

### route_planning

**Role:** Routes, distance, duration, traffic-aware driving/transit planning.

**Provider:** `baidu_lbs_provider`, `route_provider` (planner placeholders)

**Tools:** `baidu_route_mcp`, `baidu_route_matrix_mcp`, `baidu_traffic_mcp`, `baidu_geocode_mcp`, `baidu_place_search_mcp`

### review_signal

**Role:** Aggregated review/experience signals — suitability, value, crowd risk from public opinion.

**Provider:** `review_platform_provider` (placeholders), `search_provider` (fallback)

**Tools:** `review_signal_mcp`, `public_review_search_mcp`, platform review crawlers (placeholders), `search_mcp`, `browser_mcp`

**Note:** Single-review overrides are rejected by PolicyGuard; evidence must be aggregated.

### nearby_recommendation

**Role:** Food, rest areas, parking, hotels, stations near a location.

**Provider:** `baidu_lbs_provider`, `crawler_provider` / platform placeholders

**Tools:** Baidu place search/detail/reverse/route; `nearby_*_mcp` placeholders; `restaurant`, `lodging`, `fallback`

### realtime_status

**Role:** Live weather, traffic, crowd estimates.

**Provider:** `weather_provider`, `baidu_lbs_provider`, `crawler_provider` (crowd placeholders)

**Tools:** `baidu_weather_mcp`, `openmeteo_mcp`, `weather_mcp`, `baidu_traffic_mcp`, `crowd_estimation_mcp` (placeholder)

**Forbidden:** `knowledge_prior` for live facts

## Baidu Map (`baidu_lbs_provider`)

Baidu MCP tools form the **LBS foundation** for China-centric queries:

- Geo resolution and disambiguation
- POI detail (candidate hours/price/rating)
- Routing, matrix, traffic
- Short-term weather

They do not replace official ticketing pages or platform review crawlers.

## Placeholder Tools

Registered in `MCP_POLICY_SPECS` and `PLACEHOLDER_MCP_POLICIES` but **not implemented**:

- Ticket: `ctrip_ticket_crawler_mcp`, `fliggy_ticket_crawler_mcp`, …
- Reviews: `dianping_review_crawler_mcp`, `review_signal_mcp`, …
- Notes: `mafengwo_note_crawler_mcp`, `xiaohongshu_note_crawler_mcp`, …
- Nearby: `nearby_food_mcp`, `dianping_nearby_crawler_mcp`, …
- Planners: `itinerary_planner_mcp`, `route_feasibility_checker_mcp`, …
- Crowd: `crowd_estimation_mcp`, `event_calendar_mcp`

Behavior:

- Appear in `blocked_tools` with `not_implemented` or `disabled_by_config`
- Never in `allowed_tools` until a real adapter is wired
- `PolicyGuard` rejects `CALL_TOOL` with `not_implemented`

### Config flags (`.env`)

```env
ENABLE_TICKET_PLATFORM_CRAWLERS=false
ENABLE_REVIEW_PLATFORM_CRAWLERS=false
ENABLE_TRAVEL_NOTE_CRAWLERS=false
ENABLE_NEARBY_PLATFORM_CRAWLERS=false
ENABLE_ITINERARY_PLANNER_TOOLS=false
ENABLE_CROWD_ESTIMATION_TOOLS=false
```

Flags reserve future provider enablement; placeholders remain `not_implemented` until adapters exist.

## Coverage Semantics (summary)

| Evidence | Cannot fully cover |
|----------|-------------------|
| Geo / address only | `ticket_price`, reviews, seasonality |
| `price_candidate` | Official `ticket_price` (partial at best) |
| Review / experience | Opening hours, ticket price |
| Route / distance | Experience value claims |
| Realtime weather | Long-term `best_time_to_visit` / `seasonality` |
| Fallback crowd | Hard facts (price, seasonal operation) |

## Next Steps

1. Pick a provider group (e.g. `ticket_platform_provider` → Ctrip adapter).
2. Implement MCP adapter + register in `IMPLEMENTED_MCP_POLICIES`.
3. Flip the matching `ENABLE_*` flag and add integration tests.
4. Tighten `S5DomainToolBinding` capabilities and claim_types per provider.

## Code References

| Component | Path |
|-----------|------|
| Schema | `apps/agent-python/app/schemas/s5_information_domain.py` |
| Registry | `apps/agent-python/app/orchestrator/s5_information_domain_registry.py` |
| Planner | `apps/agent-python/app/orchestrator/s5_domain_planner.py` |
| Whitelist | `apps/agent-python/app/orchestrator/tool_whitelist_builder.py` |
| Placeholders | `packages/tools/mcp/adapter_status.py` |
