# Task Class Matrix Evaluation - China-only

- Time: 2026-06-27
- Runner: `python -m app.evals.run_task_class_matrix --timeout 180`
- Raw results: `apps/agent-python/debug_task_class_eval_results.json`
- Scope: 10 S5 retrieval/task classes, 2 China-only questions per class.
- Note: direct `TravelAgentStateMachine.run()` calls do not update `debug_last_session.md`; this batch writes the JSON result above.

## Summary

- Total: 20 questions.
- Returned: 18.
- Timed out: 2 (`兵马俑门票多少钱？`, `黄山和泰山哪个更适合第一次爬山？`).
- Exact task-class match: 11.
- Task-class mismatch: 7.
- Low-confidence answers (`confidence <= 0.20`): 10.
- Most frequent tools: `search_mcp` 33, `baidu_place_search_mcp` 30, `baidu_place_detail_mcp` 19, `baidu_geocode_mcp` 14.

## Test Matrix And Results

| Expected task class | Query | Resolved task class | Result | Main issue |
|---|---|---|---|---|
| `poi_recommendation` | 北京故宫附近有什么好吃的？ | `poi_recommendation` | returned | Answer is useful, but adds unrelated "地点" section and internal/mock limitations. |
| `poi_recommendation` | 杭州西湖附近有没有公共厕所？ | `poi_recommendation` | returned | It lists toilet candidates, but the conclusion says no usable toilet POI evidence. |
| `strict_fact_lookup` | 故宫博物院开放时间？ | `strict_fact_lookup` | returned | It gives `08:00-20:00`, likely suspicious for the Palace Museum; needs stronger official extraction validation. |
| `strict_fact_lookup` | 牛首山文化旅游区需要预约吗？ | `strict_fact_lookup` | returned | Over-conservative; ticket/platform evidence exists, but reservation-specific official evidence is not found. |
| `ticket_price_lookup` | 栖霞山门票价格多少？ | `ticket_price_lookup` | returned | Regressed: answer only used web candidate prices (`50 CNY`, `0 CNY`); Fliggy ticket API was not called in this run. |
| `ticket_price_lookup` | 兵马俑门票多少钱？ | - | timeout | Ticket task can exceed 180s before producing an answer. |
| `geo_fact_lookup` | 黄山主峰海拔多少米？ | `geo_fact_lookup` | returned | Fails to answer a common factual value; authoritative/encyclopedic fallback not effective. |
| `geo_fact_lookup` | 泰山海拔多少米？ | `ticket_price_lookup` | returned | Severe routing error: elevation query became ticket-price lookup and answered ticket prices. |
| `live_status` | 北京今天天气适合逛故宫吗？ | `live_status` | returned | Weather evidence exists, but answer says it cannot judge suitability because unrelated live claims are missing. |
| `live_status` | 现在去八达岭长城路上堵吗？ | `live_status` | returned | Correctly refuses real-time traffic, but exposes internal claim labels and mock/weather noise. |
| `multi_place_parallel` | 故宫和颐和园哪个更适合带老人？ | `multi_place_parallel` | returned | Fails the comparison; asks to disambiguate "故宫" instead of comparing the obvious Beijing attractions. |
| `multi_place_parallel` | 黄山和泰山哪个更适合第一次爬山？ | - | timeout | Comparison task can exceed 180s. |
| `route_first` | 从北京南站到天安门广场坐地铁怎么走？ | `strict_fact_lookup` | returned | Route query misrouted; answer contains only partial mock transit hint and unrelated fact-lookup claims. |
| `route_first` | 从杭州东站到西湖打车大概多久？ | `live_status` | returned | Route/duration query misrouted to live status and refuses instead of using route matrix/directions. |
| `review_first` | 南京大牌档口碑怎么样？ | `mixed_advisory` | returned | Review query falls back to knowledge prior; LLM composition validation failed. |
| `review_first` | 广州长隆野生动物世界排队久不久？ | `live_status` | returned | Queue/review intent collapses into live status; no useful recent review/queue synthesis. |
| `mixed_advisory` | 几月去杭州西湖最合适？ | `mixed_advisory` | returned | Generally acceptable but over-disclaims; lacks concrete source-backed seasonality evidence. |
| `mixed_advisory` | 冬天去哈尔滨旅游需要注意什么？ | `mixed_advisory` | returned | Useful basic advice, but relies heavily on low-confidence knowledge prior. |
| `minimal_probe` | 去长城玩怎么安排？ | `strict_fact_lookup` | returned | Ambiguity handling is valid, but answer includes irrelevant transit evidence for 颐和园. |
| `minimal_probe` | 树人中学附近有什么？ | `poi_recommendation` | returned | Correctly detects ambiguity, but POI evidence quality is poor and output includes internal/mock leakage. |

## Cross-cutting Problems

1. User-visible internal debug leakage remains high.
   Repeated examples include `S5 gap-fill completed ...`, `Missing source URL for Official Source Discovery`, `暂无结构化 mock 数据`, `coverage=none`, `adoption=refuse_to_guess`, and raw `claim_type` labels.

2. Limitations are not deduplicated or user-normalized.
   `关键证据不足，部分结论置信度受限。` appears in 18/20 results; `Missing source URL for Official Source Discovery` appears 15 times; date/persona assumptions appear 15 times even when irrelevant.

3. Routing is still brittle.
   Notable failures: `泰山海拔多少米？` -> `ticket_price_lookup`; route questions -> `strict_fact_lookup` / `live_status`; review questions -> `mixed_advisory` / `live_status`; broad planning -> `strict_fact_lookup`.

4. Ticket-price chain is unstable.
   `栖霞山门票价格多少？` previously could retrieve Fliggy `¥48`, but this batch did not call `fliggy_ticket_api_mcp` and returned only weak web candidates. `兵马俑门票多少钱？` timed out. Ticket lookup should make the ticket platform call a bounded early attempt for China attraction ticket queries, then stop or clearly label missing official confirmation.

5. Route/traffic tool arguments are malformed.
   Observed runtime errors include Baidu route matrix `origins is invalid`, Baidu traffic missing required `model`, Baidu weather invalid `location`, and reverse geocode schema mismatch. These cause route/live tasks to degrade into refusals.

6. Stdio MCP tools are not available in this environment.
   Repeated `[WinError 2] 系统找不到指定的文件。` appears for `browser`, `osm`, `wikidata`, and `wikipedia`. The planner should skip disabled/unlaunchable stdio MCPs after first failure, otherwise loops waste time.

7. Official-page/search fetching is noisy.
   `fetch-web` returns 400 or readable-url failures; some official extraction returns security/placeholder pages. These should be classified as failed evidence, not as low-confidence content that competes with useful sources.

8. Composer schema robustness is weak.
   Several LLM drafts failed because `limitations` was returned as a string instead of a list; one JSON output failed on unescaped quotes around `树人中学`. Fallback answers work, but quality drops sharply.

9. Evidence adoption is too strict for common factual values and too loose for unrelated claims.
   `黄山主峰海拔多少米？` refuses despite the value being a stable fact that could be corroborated by encyclopedic/geographic sources. Conversely, unrelated ticket evidence pollutes `泰山海拔多少米？`.

10. Orchestration summary is too thin.
   The JSON usually only has `{"s5_task_class": ...}`. It should include effective query count, rejected/accepted evidence IDs, failed tool families, final adopted claims, and stop reason.

## Prioritized Fix Suggestions

1. Add a response-limitation sanitizer before final response/debug export: dedupe, drop internal S5/mock/tool diagnostics, and rewrite source limitations into user-safe language.
2. Harden task routing with regression tests for the 7 mismatches above, especially elevation vs ticket, route duration vs live status, and review vs advisory/live.
3. Make China ticket-price lookup always attempt `fliggy_ticket_api_mcp` early and bounded when the query contains ticket-price intent, then rank platform facts above candidate-only search snippets.
4. Add tool-health suppression: after a stdio MCP or malformed Baidu tool call fails once for environment/schema reasons, do not repeatedly invoke that tool in the same query.
5. Fix Baidu MCP argument builders for route matrix, directions, traffic, weather, and reverse geocode.
6. Improve common-fact fallback for stable geo facts, using `search_mcp` snippets only when directly relevant and not polluted by ticket/SEO content.
7. Tighten comparison and minimal-probe policies so obvious China landmark pairs do not over-trigger disambiguation.
8. Normalize composer LLM outputs (`limitations: str -> [str]`) before Pydantic validation, and retry JSON repair for quoted Chinese entity names.
