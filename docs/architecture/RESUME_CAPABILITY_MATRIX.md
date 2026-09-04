# 简历能力事实矩阵

基线：4e339f16e0ccffce3a0e7588392e75fd1c1b5231；检查日期：2026-09-04。
状态区分：实现存在、局部测试通过、生产接线、真实服务验收。四者不能互相替代。
下列路径相对于 apps/agent-python，旧 MCP 代码路径相对于仓库根目录。

| 能力 | 实现 / production factory | 行为证据与缺口 | Live 状态 |
|---|---|---|---|
| LLM 强类型理解 | 新 PrimaryUnderstandingAdapter 已实现；app/main.py:build_runtime 仍未注入（Task 10） | tests/states/test_primary_understanding.py：严格 schema、单次 repair、鉴权/限流/超时/取消、规则回退/澄清；SDK fake HTTP 无隐藏 retry | adapter tested；live missing |
| 有界检索意图 | RetrievalPlanningHandler deterministic-v2；build_runtime 传入 Top-K | 日期/时区/约束保留、比较子任务隔离；tests/integration/test_batch_a_runtime.py 验证真实 composition root + 本地 SQLite/Qdrant + 持久化计划 | 本地生产装配通过；live missing |
| Hybrid RAG | build_runtime 接入 FTS5/BM25、Qdrant、RRF；主状态 await aretrieve | Task 4 双通道并行、独立超时、有界队列/专用 dense lane；barrier、取消、容量保留、本地持久 Qdrant 索引测试通过；指定时间过滤保留 | 本地索引通过；real embedding missing |
| SQLite 版本权威 | build_runtime 中 repository + dense validation | tests/knowledge、tests/retrieval；superseded 可重新发布、hash 只覆盖正文待加固 | Qdrant opt-in 未运行 |
| 百度 MCP | 新 BoundedStdioSession / BaiduGapTool 已实现；主链默认仍 UnavailableGapFillTool（Task 10 装配） | 固定 MCP SDK 1.29.1、百度包 1.0.5；真实独立假服务子进程验证 discovery/call/notification/EOF/timeout/cancel/schema drift/退出，无旧协议导入 | offline protocol tested；live missing |
| Transient Evidence | MCP envelope 移至共享 contracts；BaiduGapTool → normalizer → LiveGapFillHandler | 比较第二景点缺口定位；name/city/UID/来源校验；地址或明确开放时间原值及 pointer/hash/TTL；最多 1 logical gap、4 tools/call attempts；当前快照不回答历史/未来 | 离线协议到 Evidence 通过；live missing |
| Knowledge Promotion | 严格 KnowledgeCandidate/GroundingRef 已实现；pending_writer 注入点仍未装配 | candidate 禁止自带 source URL/authority/status；grounding 语义验证、发布策略、事务同步仍 missing | contract tested；live missing |
| Citation Guard | 已接主状态链 | 引用存在性/hash/status 已有；内容/景点/事实类型/时间严格支持关系待补 | missing |
| 显式状态与审计 | app/orchestration/state_machine.py | 理解路径分类；MCP schema/call/attempt/duration、预算、失败码及 gap_retried/gap_unavailable recovery；晋升审计仍待 C | 理解/MCP 局部通过；新完整链路 missing |
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

## 批次 B 验证

- Task 4–6 完成：219 passed / 1 skipped；原 13 项离线门禁通过，阈值与原 71-case 数据集未降低/删除。
- 并行检索已生产接线；LLM/MCP 在线 profile、统一生命周期及晋升入口仍属于 Task 10。
- 仅运行测试子进程，不启动真实百度 Server、不读取或调用真实 AK/LLM key。
- 详见 ../plans/2026-09-04-batch-b-verification.md。
