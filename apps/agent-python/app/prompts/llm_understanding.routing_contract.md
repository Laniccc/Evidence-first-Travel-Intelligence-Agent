# S3 AnswerModeRouter 输入契约

你的 JSON 经适配器转为 `SemanticFrame` 后，**直接**进入 S3 `AnswerModeRouter.route()`。  
以下字段必须一次填对；下游**不会**替你推断 `query_scope`、`country` 或 `can_answer_with_model_prior`。

## 1. 路由决策表（按用户问题类型填写）

| 用户意图 | query_scope | task_family | decision_type | time_scope.scope | information_needs | answer_policy |
|---------|-------------|-------------|---------------|------------------|-------------------|---------------|
| 景点/景区几月去、最佳季节 | **place** | advisory | best_time_to_visit | seasonal | best_time_to_visit, seasonality | prior=true, exact=false, live=false |
| 城市几月去、什么时候不热 | **city** | advisory | best_time_to_visit | seasonal | best_time_to_visit, seasonality | prior=true, exact=false, live=false |
| 今天几点开门/闭馆 | **place** | fact_lookup | opening_hours | **current** | opening_hours | prior=false, exact=**true**, live=false |
| 门票多少钱 | **place** | fact_lookup | ticket_price | flexible | ticket_price | prior=false, exact=**true** |
| 今天/现在人多吗 | **place** | crowd | crowd_level | **current** | crowd_level, current_crowd | prior=false, exact=false, live=**true** |
| 明天天气如何 | **place** 或 city | weather | general_advice | **current** 或 specific_date | weather, weather_today | prior=false, live=**true** |
| 适合带父母去吗 | **place** | suitability | whether_to_go | flexible | walking_intensity, accessibility, crowd_level | prior 可 true（无强事实时） |
| 多景点比较 | **place** | comparison | how_to_choose | flexible | crowd_level, transit | prior=false |
| 行程规划 | **itinerary** | planning | route_plan | flexible | transit, opening_hours | prior=false |
| 指代「这里」且无上下文 | — | — | — | — | — | needs_clarification=**true** |

**S3 关键分支：**

- `best_time_to_visit` + `query_scope ∈ {place,city,region,country}` + `can_answer_with_model_prior=true`  
  → **answer_mode = model_prior_allowed**（走 KnowledgePriorTool）
- `requires_exact_fact=true` 或 `requires_live_data=true` 或 information_needs 含 opening_hours/ticket_price/weather_today/current_crowd  
  → **answer_mode = evidence_required**
- `query_scope=place` + 有 entities 景点 + 非强事实  
  → **answer_mode = evidence_preferred**（可带 knowledge_prior 作可选）
- `needs_clarification=true` 或 missing_critical_info 含 place_reference  
  → **answer_mode = clarification_required**
- `entities` 无 **country**（Japan/China/South Korea）且非澄清  
  → RegionGate 失败 → 用户看到「不在支持范围」

## 2. 实体 entities[] 必填规则

每个地理实体一条记录，**禁止**用 `name`/`mention`，必须用 **`text`**。

| 字段 | 规则 |
|------|------|
| text | 用户原文中的称呼，如「喀纳斯湖」 |
| normalized_name | 规范名；景点可用中文或英文 |
| entity_type | natural_site / attraction / landmark / city / region / country … |
| **country** | **必填**（英文）：`Japan` / `China` / `South Korea`。景点也要填所属国家 |
| **region** | **从用户原句提取**省/州/自治区，如「新疆」「Xinjiang」「Kansai」；写在 POI 实体上即可 |
| **city** | **从用户原句提取**城市；英文或常用名，如 Sapporo、Kyoto、连云港；景区可填最近城市 |
| needs_verification | 归属不确定时 true，但 **country 仍应尽量填写**；有省/市修饰语时仍须填 `region`/`city` |
| source | llm_understanding / conversation_context / user_explicit |

**地点提取示例：**
- 「新疆的独库公路几月开放」→ 独库公路实体：`country=China`, `region=新疆`
- 「喀纳斯湖适合几月去」→ 喀纳斯湖实体：`country=China`, `region=新疆`, `city=Altay`（能推断则填）
- 「云峰山什么时候去」且无省市 → 可只填 `places`，下游可能工具消歧；**不要**因无 city 就 needs_clarification

**禁止** `query_scope=unknown` 当已识别具体景点或城市。

## 3. 地名歧义（S2 保留、S3 门控、S5 证据消歧）

- **禁止**因多地同名（衡山/白沙湖/五彩滩等）设置 `needs_clarification=true`
- 填写 `entities[].labels`（如 `primary_subject`、`ambiguous_place_candidate`）
- 有歧义时填写 `place_ambiguity`：`is_ambiguous=true` + `candidates[]`
- S3 将根据 labels 与 `place_ambiguity` 生成检索关键词，**不删减** S2 实体文本
- 最终地点确认由 S5 证据与工具完成，不在 S2/S3 提前追问用户

## 4. answer_policy 简写

填布尔字段（不要用嵌套对象）：

```json
"answer_policy": {
  "requires_live_data": false,
  "requires_exact_fact": false,
  "can_answer_with_model_prior": true,
  "must_use_official_source": false,
  "allow_partial_answer": true,
  "should_add_limitations": true
}
```

## 5. 其他字段

- `confidence`：**单个** 0~1 浮点数，禁止 `{"overall":0.9}` 对象
- `information_needs`：对象数组 `[{"need_type":"...", "priority":"high|medium|required"}]`，禁止纯字符串数组
- `time_scope`：对象 `{"scope":"seasonal|current|..."}`，禁止裸字符串

## 6. 支持区域

`supported_regions` 通常为 Japan、China、South Korea。  
识别到其他地区仍可输出实体，但 country 应如实填写以便 S3/RegionGate 判断。
