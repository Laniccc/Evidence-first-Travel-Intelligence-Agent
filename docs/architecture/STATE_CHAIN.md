# 可审计状态链

生产请求只经过 `TravelAgentStateMachine`。每个状态都接收 `StateContext`、返回 `StateResult`，转换是否合法由显式转换表校验；状态不能直接跳过证据评估或引用门禁。

```text
INGRESS → CONTEXT → UNDERSTAND → ROUTE
                              ├→ CLARIFICATION
                              ├→ FACT_QUERY ─┐
                              ├→ SUITABILITY ├→ RETRIEVAL_PLAN → HYBRID_RETRIEVE
                              └→ COMPARISON ─┘                         │
                                          ┌────────────────────────────┘
                                          ↓
                              EVIDENCE_EVALUATE ↔ LIVE_GAP_FILL
                                      │               (最多 1 个逻辑任务、2 次尝试)
                                      ├→ LIMITED_ANSWER / SAFE_FAILURE
                                      └→ COMPOSE → CITATION_GUARD
                                                        ├→ LIMITED_ANSWER / SAFE_FAILURE
                                                        └→ DELIVER
```

任一非终态还受统一运行时保护：timeout、不可恢复异常、非法转换或超过 24 步会进入 `FAILED`；图中没有画出这些安全边，但运行时会完整审计。

## 逐环节错误处理

| 状态 | 主要失败 | 有界恢复 | 审计字段 | 失败出口 |
|---|---|---|---|---|
| Ingress | 重复进行中、空输入 | 已完成请求复用；其余稳定拒绝 | 输入摘要、幂等键 | Deliver / Safe failure |
| Context | 历史服务不可用 | 降级为空历史继续 | `history_status`、恢复策略 | Understand / Safe failure |
| Understand | 模型 JSON/Schema 错误 | 修复一次，再用规则解析 | 尝试序列、解析模式 | Route / Clarification / Safe failure |
| Route | 非支持任务、景点数量不符 | 给出限定能力的澄清问题 | 请求任务、预期/实际景点数 | Clarification / Safe failure |
| Retrieval Plan | 景点无法解析 | 不猜测实体 | 子任务、事实类型、时间截面 | Clarification / Safe failure |
| Hybrid Retrieve | 通道超时、向量不可用、双通道为空 | 单通道降级或进入 gap fill | 每通道状态、延迟、失败码、降级码 | Evidence evaluate / Live gap fill / Limited answer / Safe failure |
| Live Gap Fill | 限流、超时、载荷畸形 | 同一逻辑任务最多重试 2 次 | 每次 attempt、失败码、预算 | Evidence evaluate / Limited answer / Safe failure |
| Evidence Evaluate | 缺证、冲突、非活动版本 | 权威来源优先；仍不足则拒答 | 采纳/拒绝理由、冲突证据集合 | Compose / Live gap fill / Limited answer / Safe failure |
| Compose | 模型输出解析失败 | 修复一次，再用确定性 Evidence 模板 | 生成模式、恢复策略 | Citation guard / Limited answer / Safe failure |
| Citation Guard | 引用缺失、版本/哈希不匹配 | 删除不受支持事实；硬事实失败即拒答 | claim 级引用决策 | Deliver / Limited answer / Safe failure |
| Terminal projection | 将已门禁产物映射为公共 DTO | 只读取 Citation Guard 产物 | terminal state、trace id、公开审计时间线 | HTTP response |

## 审计与回放

- `state_audit_event` 记录状态、attempt、状态结果、失败码、恢复策略、输入/输出摘要和时间。
- 原始查询、用户上下文与完整模型中间文本不进入默认审计输出；使用摘要避免泄漏。
- `SQLiteRunStore` 分开保存状态产物、Evidence、AnswerClaim、CitationDecision 和指标。
- `ReplayService` 从 `evidence_evaluate` 边界重放确定性下游，不访问检索系统；最终 Eval 将 replay consistency 作为 1.0 硬门禁。
- `StateRuntime` 统一捕获 handler 异常和超时，按 `StatePolicy` 做至多 3 次的显式尝试，并拒绝转换表之外的跳转。

实现入口：`apps/agent-python/app/orchestration/state_machine.py`、`state_runtime.py`、`transition_table.py` 和 `state_audit.py`。
