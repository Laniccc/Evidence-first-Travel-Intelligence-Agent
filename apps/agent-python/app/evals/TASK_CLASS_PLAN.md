# S5 任务类完善计划 & 测试样例

> 对照标杆：`poi_recommendation`（nearby 全链路：taxonomy → 检索 → enrichment → S5 编排 → S8 guided compose）。
> 样例用于手工回归 / 后续 `task_class_*_tests.py` 与 live eval 扩展。

---

## 总览计划表

| 序号 | S5 任务类 | PrimaryIntent | 成熟度 | 计划阶段 | 核心交付物 | 预估优先级 |
|------|-----------|---------------|--------|----------|------------|------------|
| 0 | `poi_recommendation` | NEARBY | ★★★★☆ | P0 收尾 | 评分写回 FOOD、S7 保留 RATING、点评降级 | 维持 |
| 1 | `strict_fact_lookup` | LOOKUP | ★★★☆☆ | **P1 进行中** | `fact_lookup_agent` + pipeline + `fact_lookup_guided` S8 | **高** |
| 2 | `route_first` | PLANNING | ★★☆☆☆ | P1 | `route_task_orchestration.py`、锚点→路线→可行性 S8 | **高** |
| 3 | `live_status` | REALTIME_CHECK | ★★☆☆☆ | P2 | `live_status_task_orchestration.py`、freshness 门禁 | 中 |
| 4 | `review_first` | REVIEW_CHECK | ★★☆☆☆ | P2 | `review_task_orchestration.py`、crawler 降级、复用 enrichment | 中 |
| 5 | `multi_place_parallel` | COMPARISON | ★☆☆☆☆ | P2 | 补 `comparison_tool_catalog`、并行检索、维度对齐 S8 | 中 |
| 6 | `mixed_advisory` | ADVISORY | ★☆☆☆☆ | P3 | 拆 claim 驱动子路径，抑制 search 空转 | 低 |
| 7 | `minimal_probe` | CLARIFICATION | ★★☆☆☆ | P3 | 与 `place_disambiguation` 闭环、轻量 S5 | 低 |

**通用阶段模板（每类 4 步）**

| 阶段 | 内容 | 验收 |
|------|------|------|
| A | Claim / contract 与工具目录对齐 | 单元测试：意图→task_class→whitelist |
| B | 子代理 / MCP 固定流水线 | 工具 trace 顺序可预测 |
| C | S5 编排（早停、skip、system_append） | orchestration_tests 通过 |
| D | S8 专用合成 + 5 条样例回归 | 答案字段与 evidence 一致 |

---

## 0. `poi_recommendation`（NEARBY）— 收尾

**现状**：taxonomy、周边检索、enrichment、guided compose 已通。  
**待办**：detail 评分写回 FOOD；S7 保留关联 RATING；点评 crawler 按店名补证。

| # | 测试样例（用户问句） | 期望 task / need | 通过标准（摘要） |
|---|---------------------|------------------|------------------|
| 1 | 戏马台附近有什么好吃的？ | `nearby_food` | ≥3 家餐厅；片区列表；可选门点消歧 |
| 2 | 徐州市第三中学附近有没有公共厕所？ | `nearby_toilet` | 仅厕所类 POI，不出现餐厅 |
| 3 | 故宫附近口碑好的餐厅推荐 | `nearby_food` + 口碑 | 店名 + 评分/评价证据或诚实说明缺失 |
| 4 | 户部山附近有什么停车场和好吃的？ | `nearby_parking` + `nearby_food` | 分小节两类，不交叉污染 |
| 5 | 首尔明洞附近有什么便利店？ | `nearby_supermarket` 或 `nearby_poi` | 韩国地点可锚定；品类标签合理 |

---

## 1. `strict_fact_lookup`（LOOKUP）

**计划**：`fact_lookup_task_orchestration.py`；`entity_resolution` → `fact_search` / official_discovery → official_reader；`hard_fact_strict` 早停规则。

| # | 测试样例 | 期望 claim | 通过标准 |
|---|----------|------------|----------|
| 1 | 兵马俑门票多少钱？ | `ticket_price` | 有票价 evidence；标注来源；无编造 |
| 2 | 故宫博物院开放时间？ | `opening_hours` | 营业时间 claim；优先官方页 |
| 3 | 富士山五合目现在开放吗？ | `seasonal_operation_status` | 开放/关闭状态；含日期或季节限定说明 |
| 4 | 黄山海拔多少米？ | `elevation` | 数值 + 来源；可与 wikidata/search 交叉 |
| 5 | 济州岛牛岛渡轮需要预约吗？ | `reservation_policy` | 预约政策；不足则说明缺口 |

---

## 2. `route_first`（PLANNING）

**计划**：`route_task_orchestration.py`；锚点双端解析 → `baidu_route_mcp` / matrix → 可选 traffic/weather；S8 `composer_itinerary`。

| # | 测试样例 | 期望 claim | 通过标准 |
|---|----------|------------|----------|
| 1 | 从首尔站到天安门广场开车要多久？ | `duration`, `distance` | 路线时长/距离；双端地点已解析 |
| 2 | 一天能从大阪心斋桥往返奈良东大寺吗？ | `itinerary_feasibility` | 给出往返时间判断 + 证据 |
| 3 | 上海迪士尼到浦东机场地铁怎么走？ | `route_plan`, `transit` | 公交/地铁步骤或等价 route claim |
| 4 | 从杭州东站到西湖步行多远？ | `distance`, `duration` | 步行距离；单位明确 |
| 5 | 带老人从釜山站去海云台，路上要多久？ | `duration` + 可行性提示 | 时长 + 可访问性/强度提示（有证据才写） |

---

## 3. `live_status`（REALTIME_CHECK）

**计划**：`live_status_task_orchestration.py`；`freshness_strict`；`weather_context_agent` 编排；过期证据降级。

| # | 测试样例 | 期望 claim | 通过标准 |
|---|----------|------------|----------|
| 1 | 东京今天天气怎么样？ | `weather` | 当日天气；标注检索时间 |
| 2 | 现在去八达岭长城路上堵吗？ | `traffic_status` | 路况或诚实说明无实时路况证据 |
| 3 | 釜山海云台现在人多吗？ | `crowd_level` | 人流估计或 review/crowd 信号 |
| 4 | 明后天首尔会下雨吗？ | `forecast` | 短期预报；日期对应 |
| 5 | 张家界天门山今天因天气闭园了吗？ | `seasonal_operation_status` / 公告 | 闭园/开放；强调时效性 |

---

## 4. `review_first`（REVIEW_CHECK）

**计划**：`review_task_orchestration.py`；平台 crawler → search 降级；与 nearby 口碑补证复用。

| # | 测试样例 | 期望 claim | 通过标准 |
|---|----------|------------|----------|
| 1 | 全聚德烤鸭店口碑怎么样？ | `review_summary`, `rating_candidate` | 评分/评价摘要；平台或 search 来源 |
| 2 | 济州岛黑猪肉一条街值得去吗？ | `review_summary`, `value_for_money` | 利弊要点；证据不足则明说 |
| 3 | 大阪环球影城排队久不久？ | `review_aspect`, `crowd_level` | 体验向描述；非编造排队时间 |
| 4 | 南京大牌档有什么避雷点？ | `review_aspect` | 负面/正面 aspect 分条 |
| 5 | 首尔明洞购物街和弘大哪个人更少？ | 触发 `COMPARISON` 或 review | 若走对比需两地点均有 review 维度 |

---

## 5. `multi_place_parallel`（COMPARISON）

**计划**：新增 `comparison_tool_catalog.py` 并注册；并行 per-place 检索；`aligned_dimension_comparison` S7；`composer_comparison`。

| # | 测试样例 | 期望行为 | 通过标准 |
|---|----------|----------|----------|
| 1 | 故宫和颐和园哪个更适合带小孩？ | 双景点 review + 适宜性 | 两景点均有维度；不对称作说明 |
| 2 | 东京塔和晴空塔去哪个？ | 双地点对比 | 价格/景色/人流等多维对比表 |
| 3 | 釜山和海云台市区哪个住宿更方便？ | 区域对比 | lodging/交通维度对齐 |
| 4 | 春天去武汉看樱花，东湖和武大哪个好？ | 季节 + 地点对比 | 季节性与体验证据 |
| 5 | 从时间和门票看，兵马俑和华山哪个更值得一日游？ | 时间 + 门票 + 路线 | 维度对齐；拒绝单边证据硬比 |

---

## 6. `mixed_advisory`（ADVISORY）

**计划**：按 `information_needs` 拆子路径（季节/适宜/风险）；限制无目的 search 旋转；`open_claim_advisory` 补证规则。

| # | 测试样例 | 期望 claim | 通过标准 |
|---|----------|------------|----------|
| 1 | 几月去京都最合适？ | `seasonality`, `best_time_to_visit` | 月份建议 + 依据 |
| 2 | 带三岁娃去上海迪士尼要注意什么？ | `travel_advice`, `accessibility` | 实用建议；证据驱动 |
| 3 | 第一次去韩国自由行有什么建议？ | `travel_advice` | 分点建议；标明泛化与证据边界 |
| 4 | 冬天去哈尔滨需要准备什么？ | `seasonality`, `travel_advice` | 穿衣/安全；与天气 evidence 一致 |
| 5 | 济州岛自驾和包车哪个更划算？ | `value_for_money`, `travel_advice` | 比较框架；缺价格则诚实说明 |

---

## 7. `minimal_probe`（CLARIFICATION）

**计划**：强化 `place_disambiguation`；S3→S8 澄清链；可选轻量 `entity_resolution`；`skip_s5` 默认。

| # | 测试样例 | 期望行为 | 通过标准 |
|---|----------|----------|----------|
| 1 | 去长城玩 | 歧义澄清 | 列出八达岭/慕田峪等候选；请用户选择 |
| 2 | 树人中学附近有什么？ | 地点 + 品类澄清 | 消歧学校校区；追问品类或给泛化 nearby |
| 3 | 苹果（未指明城市） | 实体澄清 | 识别歧义；不擅自假定地点 |
| 4 | 帮我查一下那个寺庙的开放时间 | 指代澄清 | 追问哪座寺庙；或基于上下文唯一化 |
| 5 | 首尔塔 | 单实体锚定 | 解析 Namsan Seoul Tower；坐标/行政区 |

---

## 建议实施顺序 & 测试文件映射

| 轮次 | 任务类 | 建议新增测试文件 |
|------|--------|------------------|
| 已完成大部分 | `poi_recommendation` | `nearby_*_tests.py`（已有，补评分样例 #3） |
| 第 1 轮 | `strict_fact_lookup` | `fact_lookup_orchestration_tests.py` |
| 第 2 轮 | `route_first` | `route_task_orchestration_tests.py` |
| 第 3 轮 | `live_status` | `live_status_orchestration_tests.py` |
| 第 4 轮 | `review_first` | `review_task_orchestration_tests.py` |
| 第 5 轮 | `multi_place_parallel` | `comparison_task_orchestration_tests.py` |
| 第 6 轮 | `mixed_advisory` | `advisory_task_orchestration_tests.py` |
| 第 7 轮 | `minimal_probe` | `clarification_task_orchestration_tests.py` |

**Live 回归**：每类至少选样例 #1、#3 做带 AK / MCP 的端到端跑（参照 `nearby_baidu_live_tests.py` 模式）。

---

## 样例速查（仅问句）

```
poi_recommendation:  戏马台附近好吃的 | 三中附近厕所 | 故宫口碑餐厅 | 户部山停车+美食 | 明洞便利店
strict_fact_lookup:  兵马俑票价 | 故宫开放时间 | 五合目开放吗 | 黄山海拔 | 牛岛渡轮预约
route_first:         首尔站→天安门驾车 | 心斋桥往返奈良一日 | 迪士尼→浦东机场地铁 | 杭州东站→西湖步行 | 釜山站→海云台老人
live_status:         东京今天天气 | 八达岭路上堵吗 | 海云台人多吗 | 首尔明后天雨 | 天门山今天闭园吗
review_first:        全聚德口碑 | 牛岛黑猪街值得吗 | 环球影城排队 | 南京大牌档避雷 | 明洞vs弘大人少
multi_place_parallel: 故宫vs颐和园带娃 | 东京塔vs晴空塔 | 釜山vs海云台住宿 | 东湖vs武大樱花 | 兵马俑vs华山一日游
mixed_advisory:      几月去京都 | 上海迪士尼带娃注意 | 韩国自由行建议 | 哈尔滨冬天准备 | 济州自驾vs包车
minimal_probe:       去长城玩 | 树人中学附近 | 苹果 | 那个寺庙开放时间 | 首尔塔
```
