# 地点解析路线图（Place Resolution）

> **当前状态**：城市级问题（如「札幌适合几月份去？」「成都什么时候去不热？」）已通过 `SemanticFrame` + `location_resolver.CITY_COUNTRY` 解析，**不依赖** mock 景点 catalog。  
> 景点级问题仍主要走 `PlaceCatalog` / `mock_data.PLACE_REGISTRY`。  
> 下列结构为**下一步**泛化目标，不与 SemanticFrame 一次性全改。

## 目标链路

```text
User Query
  → LLMPlaceEntityExtractor（从自然语言抽取 country / city / place 候选）
  → PlaceResolver（消歧、归一化、置信度）
  → 按优先级查证据源：
       RealPlaces / MCP Places / LocalCache
       → MockCatalog fallback（仅最后兜底）
  → SemanticFrame.entities 填充
```

## 组件职责（待实现）

| 组件 | 职责 |
|------|------|
| `LLMPlaceEntityExtractor` | structured output：`PlaceCandidate[]`（name, type, confidence） |
| `PlaceResolver` | 候选 → 规范名 + country/city；处理别名与歧义 |
| `RealPlacesTool` / `places_mcp` | 真实地理编码与 POI |
| `LocalCache` | `tool_cache` 扩展 place 维度 TTL |
| `MockPlaceCatalogBackend` | **fallback only**，不再作为主路径 |

## 与 SemanticFrame 的关系

- **SemanticFrame** 只消费 `entities`（country / city / places），不关心解析实现。
- **AnswerModeRouter** 根据 `query_scope`（city vs place）决定 model prior 或 evidence，**不要求** mock catalog 有该景点。
- 城市级 advisory（`best_time_to_visit`）只需 `city + country`，由 `resolve_city_country_from_text` 或未来 `PlaceResolver` 提供。

## 近期已做

- `CITY_COUNTRY` 扩展：`札幌/Sapporo`、`成都/Chengdu` 等
- `SemanticFrameBuilder.build_city_best_time()` 显式产出城市季节帧
- `RuleBasedUnderstanding` 在 QU 阶段直接附加 `semantic_frame`

## 验收标准（下一阶段）

1. 「成都什么时候去不热？」在无 `PLACE_REGISTRY` 条目时仍能 `query_scope=city` 并回答
2. 景点名不在 mock 库时，`PlaceResolver` 可经 RealPlaces 返回坐标/地址 Evidence
3. mock catalog 仅出现在 `tool_trace.fallback_used=true` 路径
