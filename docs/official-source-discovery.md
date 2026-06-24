# Official Source Discovery

S5 discovers official-source **candidates** from search hits; S7 judges whether they support each claim.

## Responsibility split

| Stage | Role |
|-------|------|
| **S5** `official_source_discovery_mcp` | Classify URLs (domain, title, snippet signals). Emit `official_source_candidate` evidence. No ticket price conclusion. |
| **S7** `official_source_judgement` | Map `source_class` + field signals (`has_ticket_info`, etc.) to coverage tier: `strong` / `partial` / `weak` / `none`. Drive adoption, coverage, conflicts, gap requests. |
| **S8** Answer composer | Existing rules: do not present OTA/review pages as official sites. |

## Flow (example: 束河古镇 ticket_price)

1. `search_mcp` returns gov page, Ctrip page, sogou redirect wrapper.
2. `official_source_discovery_mcp` classifies each URL → `official_source_candidate` evidence with structured `normalized_value`.
3. S7: gov heritage page → `weak` for `ticket_price` (background only); Ctrip → `partial` at best → `candidate_only` adoption.
4. Gap planner emits `EvidenceGapRequest` with `official_source_discovery_mcp` + official query templates.
5. Optional: `official_page_reader_mcp` fetches **direct** URLs only (redirect wrappers skipped).

## `source_class` values

| Class | Meaning |
|-------|---------|
| `official_government` | `.gov.cn` / government site |
| `tourism_board_official` | Tourism board / 文旅局 |
| `scenic_operator_official` | Scenic operator official site |
| `scenic_operator_official_candidate` | Likely operator, not fully verified |
| `authorized_platform_candidate` | Platform with ticket signal |
| `ota_platform` / `review_platform` | Ctrip, Dianping, etc. |
| `seo_content_site` | Guides, sogou/baidu redirect wrappers |
| `not_official` | Rejected |

## Claim-level rules (S7)

- **ticket_price**: `strong` only for official class + `has_ticket_info`; gov background without price → `weak`; OTA → `candidate_only`.
- **opening_hours**: official + `has_opening_hours` → `strong`; map/OTA hours → `partial`.
- **seasonal_operation_status** / **road_opening_period**: official + `has_notice_info` → `strong`.
- **destination_background**: gov/tourism pages → `strong`/`partial`.
- **review_signal**: official classes do not boost; review/OTA platforms scored normally.

## ToolTrace fields

When `official_source_discovery_mcp` runs:

- `official_source_discovery`: `true`
- `urls_checked_count`: number of search hits processed
- `official_candidates_count`: candidates emitted
- `top_source_classes`: top 5 `source_class` values

## Configuration

```env
OFFICIAL_SOURCE_DISCOVERY_ENABLED=true
```

Default: enabled. Local Python tool (not an external MCP server).

## Tests

```powershell
cd apps/agent-python
pytest app/evals/official_source_tests.py -q
```
