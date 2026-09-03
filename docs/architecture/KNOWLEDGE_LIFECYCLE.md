# 动态景点知识生命周期

RAG 只管理少量、可评测的景点事实：开放时间、票价、预约、交通、无障碍、游客须知和简介。它不是通用旅游内容仓，也不抓取评论、周边商户或行程。

## 权威模型

SQLite 是事实与版本的唯一权威存储；Qdrant 只是可重建的稠密索引。

```text
Source → KnowledgeDocument → DocumentVersion → FactChunk
                                      │
                                      └→ IndexGeneration → Qdrant point
```

每个可引用 chunk 都携带：`source_id`、URL、来源类型、`document_version_id`、事实类型、有效期、内容哈希、来源权威度与 corpus version。回答只引用最终检索报告中的完整 provenance。

## 状态转换

| 当前状态 | 操作 | 新状态 | 约束 |
|---|---|---|---|
| pending | publish | active | 同一来源的旧 active 版本原子变为 superseded |
| pending | reject | rejected | 必须记录原因，不进入索引 |
| active | 到达 `valid_to` | expired | 查询时间过滤，不能泄漏 |
| active | 发布新版本 | superseded | 旧 chunk 从下一代索引移除 |
| superseded / expired / rejected | 任意检索 | 不变 | SQLite 和 Qdrant 后过滤均拒绝 |

## 写入与索引闭环

1. `python -m app.evidence.knowledge.cli seed` 校验 fixture，并按参数写入 pending 或直接发布。
2. `refresh --source-id ...` 对指定来源重新摄取，内容未变化时保持幂等，变化时产生 pending 版本。
3. `publish --version-id ...` 激活审核后的版本，并原子 supersede 同一来源的旧 active 版本。
4. 到达 `valid_to` 的版本在查询时间被视为 expired，不会进入召回结果。
5. `reindex` 从 SQLite 的 active chunks 构建新 generation。
6. generation 的数量与内容哈希核对成功后才切换 active；失败 generation 不替换线上版本。
7. 切换后清理旧 generation；清理失败会记录，但不会回滚已验证的新 generation。

## 一致性原则

- 词法检索直接查询 SQLite FTS5，并按 active 状态和时间过滤。
- 稠密召回必须携带 corpus、模型、景点和事实类型过滤；返回后再次用 SQLite 校验版本状态与内容哈希。
- Qdrant 中的陈旧或人为注入 point 会被 post-filter 拒绝并写入 RetrievalReport。
- 相同 corpus + embedding model 的重建是幂等的；最终 Eval 要求 index rebuild consistency = 1.0。

完整可复制命令见根目录 `RUNBOOK.md`。相关实现：`app/evidence/knowledge/`、`app/evidence/retrieval/index_sync.py`、`app/integrations/qdrant/vector_index.py`。
