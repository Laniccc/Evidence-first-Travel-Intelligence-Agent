# Hybrid RAG 检索

检索目标不是“尽量多找内容”，而是在指定景点、事实类型和时间截面下返回可引用的活动版本证据。

```text
RetrievalPlan
   ├─ SQLite FTS5 lexical ─┐
   └─ Qdrant dense ────────┼─ RRF fusion ─ metadata/version/hash filter
                           └─────────────── authority + freshness rerank
                                                ↓
                                         RetrievalReport
```

## 检索契约

`RetrievalPlan` 固定包含 `task_type`、查询文本、景点 ID、事实类型、`as_of`、top-k 和隔离的 subtask ID。比较任务为每个景点生成独立计划，证据不能跨景点串用。

`RetrievalReport` 同时记录 lexical/dense 两个通道的状态、数量、延迟和失败码，RRF 候选、后过滤拒绝原因、最终排序、corpus version 和降级方式。因此一次“成功回答”也能说明是否发生过通道失败。

## 降级矩阵

| Lexical | Dense | 行为 | Degradation |
|---|---|---|---|
| 成功 | 成功 | 融合、过滤、重排 | none |
| 成功 | 超时/embedding 不可用 | 使用词法结果 | lexical_only |
| 失败 | 成功 | 使用稠密结果 | dense_only |
| 空 | 空 | 进入一次 live gap-fill | no_results |
| 失败 | 失败 | 记录双通道失败并 gap-fill；仍无证则拒答 | all_failed |

异常不会静默吞掉：每个通道有独立 `failure_code`，恢复动作进入状态审计。最终 Evidence Evaluate 和 Citation Guard 仍会检查来源、版本、冲突和 claim-evidence 对应关系。

## 消融解释

离线报告同时列出 lexical-only、dense-only、hybrid、hybrid+rerank。`hybrid` 使用 RRF 并保留强制版本/哈希安全过滤，但按 RRF 顺序输出；`hybrid+rerank` 再加入来源权威度和新鲜度排序。当前 deterministic hash embedding 用于完全离线、可重复的控制面回归；四组得分一致时，只能说明 fixture 上的编排、过滤和排序门禁正确，不能宣称真实语义检索优于词法检索。真实 embedding profile 是后续可选验证，不属于 CI。

Qdrant Docker 配置是单机作品集实现，只演示带 API key 的服务边界和可重建索引；不宣称高可用、备份、容灾或生产集群能力。
