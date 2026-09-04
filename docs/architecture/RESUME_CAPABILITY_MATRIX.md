# 简历能力事实矩阵

基线：4e339f16e0ccffce3a0e7588392e75fd1c1b5231；检查日期：2026-09-04。
状态区分：实现存在、局部测试通过、生产接线、真实服务验收。四者不能互相替代。
下列路径相对于 apps/agent-python，旧 MCP 代码路径相对于仓库根目录。

| 能力 | 实现 / production factory | 行为证据与缺口 | Live 状态 |
|---|---|---|---|
| LLM 强类型理解 | build_runtime 在 online 且有凭据时注入 PrimaryUnderstandingAdapter + SingleAttemptLLMClient | 单次 repair、鉴权/限流/超时/规则回退；test_online_runtime_wiring 从真实应用入口经 SDK fake HTTP 走 model 路径 | production wired / offline tested；live missing |
| 有界检索意图 | RetrievalPlanningHandler deterministic-v2；build_runtime 传入 Top-K | 日期/时区/约束保留、比较子任务隔离；tests/integration/test_batch_a_runtime.py 验证真实 composition root + 本地 SQLite/Qdrant + 持久化计划 | 本地生产装配通过；live missing |
| Hybrid RAG | build_runtime 接入 FTS5/BM25、Qdrant、RRF；主状态 await aretrieve | Task 4 双通道并行、独立超时、有界队列/专用 dense lane；barrier、取消、容量保留、本地持久 Qdrant 索引测试通过；指定时间过滤保留 | 本地索引通过；real embedding missing |
| SQLite 版本权威 | repository、v2 canonical hash、版本来源快照与幂等迁移；dense hit 二次验证保留 | 拒绝 reactivation/到期发布/换绑；chunks/TTL 变化新版本；历史 FTS/引用保留；事务 outbox、lease/CAS、重启恢复、实际索引一致性检查 | 本地持久 Qdrant 通过；server opt-in 未运行 |
| 百度 MCP | build_runtime online + BOUNDED_BAIDU_ENABLED 装配 BoundedStdioSession / BaiduGapTool | 固定 SDK 1.29.1/百度包 1.0.5；真实应用生命周期 + 独立假 stdio 进程验证调用与退出；缺凭据/启动故障 readiness 分类 | production wired / offline protocol tested；live missing |
| Transient Evidence | MCP envelope 移至共享 contracts；BaiduGapTool → normalizer → LiveGapFillHandler | 比较第二景点缺口定位；name/city/UID/来源校验；地址或明确开放时间原值及 pointer/hash/TTL；最多 1 logical gap、4 tools/call attempts；当前快照不回答历史/未来 | 离线协议到 Evidence 通过；live missing |
| Knowledge Promotion | CandidateExtractor + 五层 validator + PromotionService + SQLite outbox；显式 knowledge_promote 接生产链 | stable address 经许可自动发布、开放时间 pending、默认禁留存；写失败回滚、Qdrant 失败恢复；仅精确 extraction，不宣称语义蕴含 | production wired / offline tested；live missing |
| Citation Guard | 已接主状态链 | 引用存在性/hash/status 已有；内容/景点/事实类型/时间严格支持关系待补 | missing |
| 显式状态与审计 | state_machine + knowledge_promote；真实 create_app/build_runtime 生命周期 | 一次晋升后仅走评估预定出口；失败保留 transient；run/query/trace 贯穿工具、候选、发布、job；恢复失败码持久化 | 新生产路径离线通过；严格 Citation 与终态审计待 D |
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

## 批次 C 验证

- Task 7–10 完成：256 passed / 1 skipped；原 71-case、13 项 Eval 门禁通过。新增 37 个单元/集成案例尚未并入新增发布门禁。
- 生产入口已装配模型、stdio MCP、临时证据、受控候选、原子发布与后台索引恢复；测试只用假 HTTP/独立假 stdio 子进程、本地持久 Qdrant，不调用真实服务。
- 自动发布需要独立留存许可配置，默认关闭；关闭知识入库不等于删除运行审计。真实数据留存/审计许可仍须确认。
- Task 11–14 的 Citation 深度校验、transient Replay、后续 dense-only Hit 发布级回归、新门禁、Java/Web 观测与真实 smoke 尚待 D。
- 详见 ../plans/2026-09-04-batch-c-verification.md。
