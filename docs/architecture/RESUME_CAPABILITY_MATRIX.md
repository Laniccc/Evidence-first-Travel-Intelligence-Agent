# 简历能力事实矩阵

基线：4e339f16e0ccffce3a0e7588392e75fd1c1b5231；检查日期：2026-09-04。
状态区分：实现存在、局部测试通过、生产接线、真实服务验收。四者不能互相替代。
下列路径相对于 apps/agent-python，旧 MCP 代码路径相对于仓库根目录。

| 能力 | 实现 / production factory | 行为证据与缺口 | Live 状态 |
|---|---|---|---|
| LLM 强类型理解 | app/main.py:build_runtime 未注入 primary_understanding | tests/states/test_understand_route.py 仅注入式 repair/fallback；严格 adapter missing | missing |
| 有界检索意图 | app/orchestration/states/retrieval_planning.py | tests/states/test_retrieval_planning.py；固定 top_k/clock，明确日期与约束未保留 | missing |
| Hybrid RAG | build_runtime 接入 FTS5/BM25、Qdrant、RRF | tests/retrieval；当前串行，中文自然问句召回待补 | real embedding missing |
| SQLite 版本权威 | build_runtime 中 repository + dense validation | tests/knowledge、tests/retrieval；superseded 可重新发布、hash 只覆盖正文待加固 | Qdrant opt-in 未运行 |
| 百度 MCP | 主链默认 UnavailableGapFillTool；packages/tools/mcp/adapters/baidu_map_adapter.py 为旧实现 | 旧 stdio_client.py 使用 Content-Length；官方 SDK 和生产接线 missing | missing |
| Transient Evidence | app/evidence/claim_decision.py + live gap handler | tests/states 中注入式行为；完整来源封装 missing | missing |
| Knowledge Promotion | pending_writer 注入点存在 | 严格 candidate、grounding、发布策略、事务同步 missing | missing |
| Citation Guard | 已接主状态链 | 引用存在性/hash/status 已有；内容/景点/事实类型/时间严格支持关系待补 | missing |
| 显式状态与审计 | app/orchestration/state_machine.py | tests/states；新增 LLM/MCP/晋升错误分类需扩展 | 新链路 missing |
| Replay | 持久化 retrieval_plan/hybrid_retrieve | transient/MCP/晋升旁支回放 missing | 不宣称在线确定性 |
| Eval | evals.runner 原 71 个受控案例 | 原 13 门禁通过；hash embedding，不代表真实语义召回；新场景门禁 missing | missing |

## 本轮可复现基线

- python -m pytest -q：127 passed, 1 skipped；跳过为真实 Qdrant opt-in，另有 Starlette/httpx 弃用警告。
- python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/generated/batch-a-baseline.json：exit 0，原 13 项门禁通过。
- generated 路径为忽略的运行产物，未覆盖已提交评测基线；执行者应自行重跑。
- 本批不改变 Java-Python 公共 DTO，不把内部新契约冒充端到端生产验收。
