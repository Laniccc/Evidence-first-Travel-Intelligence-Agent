# 简历能力事实矩阵

基线：4e339f16e0ccffce3a0e7588392e75fd1c1b5231；检查日期：2026-09-04。
状态区分：实现存在、局部测试通过、生产接线、真实服务验收。四者不能互相替代。
下列路径相对于 apps/agent-python，旧 MCP 代码路径相对于仓库根目录。

| 能力 | 实现 / production factory | 行为证据与缺口 | Live 状态 |
|---|---|---|---|
| LLM 强类型理解 | 新 PrimaryUnderstandingAdapter 已实现；app/main.py:build_runtime 仍未注入（Task 10） | tests/states/test_primary_understanding.py：严格 schema、单次 repair、鉴权/限流/超时/取消、规则回退/澄清；SDK fake HTTP 无隐藏 retry | adapter tested；live missing |
| 有界检索意图 | RetrievalPlanningHandler deterministic-v2；build_runtime 传入 Top-K | 日期/时区/约束保留、比较子任务隔离；tests/integration/test_batch_a_runtime.py 验证真实 composition root + 本地 SQLite/Qdrant + 持久化计划 | 本地生产装配通过；live missing |
| Hybrid RAG | build_runtime 接入 FTS5/BM25、Qdrant、RRF | tests/retrieval；当前仍串行；自然中文使用有界事实词/前缀，dense query 不被词法串覆盖；指定时间需要明确有效区间 | real embedding missing |
| SQLite 版本权威 | build_runtime 中 repository + dense validation | tests/knowledge、tests/retrieval；superseded 可重新发布、hash 只覆盖正文待加固 | Qdrant opt-in 未运行 |
| 百度 MCP | 主链默认 UnavailableGapFillTool；packages/tools/mcp/adapters/baidu_map_adapter.py 为旧实现 | 旧 stdio_client.py 使用 Content-Length；官方 SDK 和生产接线 missing | missing |
| Transient Evidence | 新不可变 MCP envelope + TransientEvidence.from_verified_payload；旧 fixtures 兼容 | tests/knowledge/test_candidate_contracts.py 验证 schema/hash/时间/URL 与必填来源字段；新的 MCP adapter 尚未实现；当前快照不能证明指定历史/未来时间 | contract tested；live missing |
| Knowledge Promotion | 严格 KnowledgeCandidate/GroundingRef 已实现；pending_writer 注入点仍未装配 | candidate 禁止自带 source URL/authority/status；grounding 语义验证、发布策略、事务同步仍 missing | contract tested；live missing |
| Citation Guard | 已接主状态链 | 引用存在性/hash/status 已有；内容/景点/事实类型/时间严格支持关系待补 | missing |
| 显式状态与审计 | app/orchestration/state_machine.py | 理解输出区分 model/repair/rule/clarification，记录安全 failure code 与版本；MCP/晋升审计待后续批次 | LLM 局部测试通过；新完整链路 missing |
| Replay | 持久化 retrieval_plan/hybrid_retrieve | transient/MCP/晋升旁支回放 missing | 不宣称在线确定性 |
| Eval | evals.runner 原 71 个受控案例 | 原 13 门禁通过；hash embedding，不代表真实语义召回；新场景门禁 missing | missing |

## 本轮可复现基线

- python -m pytest -q：127 passed, 1 skipped；跳过为真实 Qdrant opt-in，另有 Starlette/httpx 弃用警告。
- python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/generated/batch-a-baseline.json：exit 0，原 13 项门禁通过。
- generated 路径为忽略的运行产物，未覆盖已提交评测基线；执行者应自行重跑。
- 本批不改变 Java-Python 公共 DTO，不把内部新契约冒充端到端生产验收。

## 批次 A 验证

- 完成 Task 0–3；Python 全量 188 passed / 1 skipped，原 13 项离线门禁全部通过。
- 原 retrieval suite 20 cases：Recall@3 / MRR / NDCG@5 / metadata_filter_accuracy / provenance_completeness 均为 1.0；这是受控 hash-embedding 评测，不是在线真实效果。
- 详细记录见 ../plans/2026-09-04-batch-a-verification.md；本轮没有调用真实 LLM / 百度服务，没有进行真实 Qdrant server smoke。
- 仅有 adapter 与契约不能支持简历中“LLM + MCP + 自动知识晋升已完整接通”的声明。
