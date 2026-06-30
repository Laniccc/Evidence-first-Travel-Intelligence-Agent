# Non-Lookup Task Chains

This note documents the task-class layer added for non-lookup intents. It keeps the
Evidence-first split intact:

- S5 plans retrieval domains, provider families, allowed tools, and blocked tools.
- S7 evaluates Evidence and applies task-specific adoption levels.
- S8 receives a task profile, debug trace, adoption summary, and draft structure.

No destination facts are hardcoded here. User-visible factual values must come from
`Evidence` and `ClaimDecision`.

## Task Classes

| task_class | state chain | primary source families |
| --- | --- | --- |
| advisory | Context -> Understanding -> AdvisoryContract -> RegionGate -> AdvisoryEvidencePlanning -> EvidenceAccumulation -> AdvisoryEvidenceJudge -> AdvisoryComposer | review, seasonality/weather, route, official when hard/live subclaims appear |
| review_check | Context -> Understanding -> ReviewCheckContract -> ReviewSignalRetrieval -> EvidenceAccumulation -> ReviewSignalAggregation -> ReviewInsightComposer | review platforms, public search/crawlers, weak map detail candidates |
| planning | Context -> Understanding -> PlanningContract -> RegionGate -> PlanningEvidenceRetrieval -> EvidenceAccumulation -> RouteFeasibilityJudge -> optional gap fill -> ItineraryComposer | geo, route matrix/planning, opening hours, traffic/weather, review difficulty |
| comparison | Context -> MultiPlaceUnderstanding -> ComparisonContract -> MultiPlaceEvidenceRetrieval -> EvidenceAccumulation -> AlignedComparisonJudge -> ComparisonComposer | per-place geo, review, route, operation/ticket when relevant |
| nearby | Context -> NearbyUnderstanding -> NearbyContract -> NearbyPOIRetrieval -> EvidenceAccumulation -> NearbyCandidateJudge -> NearbyRecommendationComposer | geo/nearby map, place detail, route, review/crawler enrichment |
| realtime_check | Context -> RealtimeUnderstanding -> RealtimeContract -> RealtimeEvidenceRetrieval -> EvidenceAccumulation -> FreshnessJudge -> RealtimeComposer | weather, traffic/map, official notice/page, event/crowd proxies |
| clarification | Context -> Understanding -> ClarificationPolicy -> optional minimal probe -> ClarificationComposer -> END | minimal geo/search probe only |

## Debug Trace

`app.orchestrator.non_lookup_task_chains.build_non_lookup_task_debug_trace` emits:

- `task_class`
- `task_chain`
- `selected_state_path`
- `primary_claims`
- `secondary_claims`
- `source_family_plan`
- `allowed_tools`
- `blocked_tools`
- `attempted_source_families`
- `skipped_with_reason`
- `evidence_count_by_family`
- `claim_decisions`
- `adoption_levels`
- `user_visible_limitations`
- `internal_debug_limitations`

`internal_debug_limitations` is kept separate from user-visible limitations.

## Local Sample Trace Summary

Generated locally from `build_sample_trace_summaries()`:

```text
advisory: chain=8, claims=review_summary,seasonality,route_plan, families=baidu_lbs_provider,search_provider,review_platform_provider
review_check: chain=7, claims=review_summary,value_for_money,crowd_risk, families=baidu_lbs_provider,search_provider,review_platform_provider
planning: chain=9, claims=route_plan,duration,distance, families=baidu_lbs_provider,search_provider,route_provider
comparison: chain=7, claims=review_summary,route_plan,duration, families=baidu_lbs_provider,search_provider,review_platform_provider
nearby: chain=7, claims=nearby_poi,nearby_food, families=baidu_lbs_provider,search_provider,review_platform_provider
realtime_check: chain=7, claims=current_weather,traffic_status,current_crowd, families=baidu_lbs_provider,search_provider,weather_provider
clarification: chain=6, claims=entity_resolution,disambiguation, families=baidu_lbs_provider,search_provider
```
