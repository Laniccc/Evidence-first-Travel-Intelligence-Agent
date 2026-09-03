# Project Mainline

## 一句话定位

这是一个小而闭环的 Evidence-first Travel Agent：用显式状态机回答景点事实、适合度与双景点比较，用版本化 Hybrid RAG 管理动态事实，并把失败、恢复、引用和回放变成可评测的发布门禁。

## 主链

```text
Web
  → Java Platform（用户、会话、记录、收藏）
    → Python Agent（一次 run）
      → Ingress → Context → Understand → Route
        → Fact Query / Suitability / Comparison
          → Retrieval Plan → Hybrid Retrieve
            → Evidence Evaluate ↔ bounded Live Gap Fill
              → Compose → Citation Guard → Deliver
```

证据不足、版本失效、冲突无法消解或引用不完整时，链路进入 `limited_answer` / `safe_failure`，而不是补写模型先验。每个状态记录 attempt、结果、失败码、恢复策略和安全摘要；回放从持久化产物开始，不再次访问外部依赖。

## 数据权威

- SQLite/FTS5 是来源、版本、chunk、有效期与索引 generation 的唯一事实权威。
- Qdrant 是可删除、可重建的 dense 索引，不拥有业务真相。
- 所有可交付硬事实必须对应活动版本 Evidence、来源 URL、版本 ID 和内容哈希。
- 检索输出是 `RetrievalReport`，成功、降级、后过滤拒绝和通道错误都可观察。

## 系统所有权

- Java：用户、认证、会话、查询历史、收藏、profile，以及未来计费/订阅。
- Python：理解、路由、检索计划、Evidence、回答 claim、引用决策、run 审计与回放。
- Web：只调用 Java，并呈现来源、版本、检索降级、引用结果和安全审计。

Java-Python 契约变更必须同时有 Python API/contract 测试与 Java client/platform flow 测试；前端行为变更必须先覆盖平台返回契约。

## 明确不做

行程生成、周边推荐、评论挖掘、票务爬虫、人流估算、通用旅游问答和 Neo4j/Graph-RAG 已从运行时移除。保留 `ticket_price` 是为了将票价作为动态、可追踪、可过期的知识事实，而不是恢复票务能力。

Qdrant compose 只展示带认证的单机服务边界；项目不声称已经实现 HA、备份、灾备、在线学习或真实中文 embedding 的语义增益。

## 完成定义

主线只有在以下条件同时成立时可交付：

1. Python、Java 和 Web 测试通过，Web 可构建，Qdrant compose 可解析。
2. 71-case 离线 Eval 的 13 个硬门禁全部通过。
3. 非活动版本泄漏、非法状态转换、无来源硬事实均为 0。
4. 文档命令可直接映射到仓库中的真实入口。

详见 [STATE_CHAIN.md](docs/architecture/STATE_CHAIN.md)、[KNOWLEDGE_LIFECYCLE.md](docs/architecture/KNOWLEDGE_LIFECYCLE.md)、[HYBRID_RETRIEVAL.md](docs/architecture/HYBRID_RETRIEVAL.md)、[EVALS.md](docs/architecture/EVALS.md) 和 [RUNBOOK.md](RUNBOOK.md)。
