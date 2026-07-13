## 输入

```json
{
  "raw_user_query": "{{raw_user_query}}",
  "conversation_context": {{conversation_context}},
  "current_date": "{{current_date}}",
  "supported_regions": {{supported_regions}},
  "evidence_policy_summary": {{evidence_policy_summary}}
}
```

## 输出要求

返回 **一个** NormalizedUserRequest JSON 对象，供 S3 AnswerModeRouter 直接消费。

### 填写前自检（必须全部满足）

1. `raw_query` = 用户原句；`rewritten_query` = 结构化转写（仍不回答事实）
2. **从 `raw_user_query` 提取地点锚点**：省/自治区/直辖市/城市/州 → 写入 `entities[].region` / `city`（挂在被问景点/道路上）
3. 若已识别景点/道路/景区 → `query_scope=place`，`entities` 含该主体且 **`country` 已填**
4. 若已识别城市 → `query_scope=city`，`entities` 含城市且 **`country` 已填**
5. 季节/几月去 → `decision_type=best_time_to_visit`，`time_scope.scope=seasonal`，`answer_policy.can_answer_with_model_prior=true`
6. 今日开放/关门/票价/实时天气/人流 → `answer_policy.can_answer_with_model_prior=false`，并设 `requires_exact_fact` 和/或 `requires_live_data`
7. `entities[].text` 存在；**不要用 name**
8. `confidence` 为单个数字 0~1
9. 「这里/那边」且 context 无法解析 → `needs_clarification=true`，`missing_critical_info` 含 `place_reference`
10. **禁止**因仅有景点名、无 city 就把 `needs_clarification=true`——若原文含「新疆/云南/江苏…」等，必须填入 `region`

只输出 JSON，不要其他文字。
