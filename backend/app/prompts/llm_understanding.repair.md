上一次输出的 NormalizedUserRequest **未通过 Pydantic 校验或未满足 S3 路由契约**。

## 校验错误
{{validation_error}}

## 用户原句
{{raw_user_query}}

## 修复要求

1. 只输出**一个**合法 JSON 对象，字段名与 NormalizedUserRequest Schema 完全一致。
2. 使用 `entities[].text`，不要用 `name` / `mention`。
3. `confidence` 必须是 0~1 的**数字**，不是对象。
4. 若问题涉及具体景点/城市：`query_scope` 不得为 unknown；`entities[].country` 必填（Japan/China/South Korea）。
5. 季节建议类：`decision_type=best_time_to_visit`，`answer_policy.can_answer_with_model_prior=true`。
6. 强事实类：`can_answer_with_model_prior=false`，`requires_exact_fact=true` 或 `requires_live_data=true`。

不要 markdown，不要解释。
