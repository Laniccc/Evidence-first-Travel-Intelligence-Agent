# Eval 与发布门禁

离线 Eval 是本项目的交付核心，而不是演示脚本。数据集覆盖检索质量、元数据与版本隔离、状态路由、证据冲突、故障恢复、引用安全、连续对话、比较隔离、索引幂等和审计回放。

## 一键运行

```powershell
cd apps/agent-python
python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/final-offline.json
```

命令同时生成 JSON 机器报告和同名 Markdown 摘要；任一硬门禁失败时退出码为 1。CI 不调用真实 LLM，也不下载 embedding model。

## 数据集分布

| 领域 | Cases |
|---|---:|
| Hybrid retrieval | 20 |
| Metadata/version lifecycle | 20 |
| State routing | 8 |
| Evidence conflict | 6 |
| Citation | 7 |
| Failure recovery | 6 |
| Multi-turn/comparison | 4 |
| LLM understanding/repair/fallback | 8 |
| MCP stdio recovery | 8 |
| Knowledge promotion | 16 |
| Adversarial grounding | 8 |
| Miss → promote → sync recovery → dense-only hit → replay | 1 |
| 合计 | 112 |

## 硬门禁

| 指标 | 门槛 | 当前离线结果 |
|---|---:|---:|
| Recall@3 | ≥ 0.90 | 1.00 |
| MRR | ≥ 0.85 | 1.00 |
| nDCG@5 | ≥ 0.90 | 1.00 |
| Metadata filter accuracy | = 1.00 | 1.00 |
| Expired/superseded leakage | = 0 | 0 |
| State path accuracy | ≥ 0.95 | 1.00 |
| Illegal transitions | = 0 | 0 |
| Stale vector rejection | = 1.00 | 1.00 |
| Index rebuild consistency | = 1.00 | 1.00 |
| Unsupported hard facts | = 0 | 0 |
| Citation precision | ≥ 0.95 | 1.00 |
| Abstention precision | ≥ 0.90 | 1.00 |
| Replay consistency | = 1.00 | 1.00 |
| Unsafe auto publish | = 0 | 0 |
| Provenance fabrication | = 0 | 0 |
| Promotion idempotency | = 1.00 | 1.00 |
| Sync recovery | = 1.00 | 1.00 |
| Miss → promote → dense hit | = 1.00 | 1.00 |
| MCP budget violations | = 0 | 0 |
| Replay external calls | = 0 | 0 |
| Replay knowledge/index write side effects | = 0 | 0 |

原 13 门禁及阈值保持不变；新增 8 门禁。每个业务案例还必须通过 expected/actual 检查，包括原 conflict、recovery、conversation，不允许总体均值隐藏单例错误。

当前验证记录：[Task 11–13 检查点](../plans/2026-09-04-batch-d-safety-verification.md)。本地最新报告路径为 `apps/agent-python/evals/reports/generated/batch-d-task13.json`，运行产物不入 Git；已提交的 `final-offline.md/json` 是旧 71-case 基线，不代表本轮结果。

## BadCases 与诚实边界

`bad_cases` 包含 case_id、expected、actual、state、failure_code、artifact_refs。单例与指标失败都使 all + fail-on-regression 返回 1；mutation 测试真实调用 CLI 入口验证该行为。指针引用同一 JSON 内的实际观测，生产闭环保留首次 gap/promotion、索引失败/恢复、第二次 retrieval/citation 的产物，不只留无法再读取的临时数据库路径。

候选被拒绝与最终泄漏硬事实是不同指标：14 个不合规候选应拒绝，8 个对抗 claim 应移除；这些安全拒绝不会增加已交付 unsupported facts。正常稳定地址自动发布，开放时间仅 pending/manual review。

离线闭环通过真实 build_runtime、SDK fake HTTP、独立 fake stdio 进程、本地 SQLite 与 Qdrant。索引写入先注入超时，再由持久任务恢复；第二次查询禁用 lexical 并禁止 MCP，必须从新 generation 命中第一次晋升的版本。Replay 阶段对模型/工具/知识写入/索引方法设禁用探针，并检查数据库计数不变；仅允许新建 replay 审计记录。

四组消融均为通道上限 20、融合候选上限 8、最终 Top-K 5，并共用不截断的安全过滤。lexical/dense 保留各通道秩序，hybrid 使用 RRF，hybrid+rerank 才增加权威性和时效性重排；不通过非法 top_k 绕过契约。

当前结果不等于线上泛化能力：hash embedding 不衡量中文语义质量，也没有覆盖高并发、真实网络抖动或跨语言召回。real-embedding profile 额外加入 `retrieval_semantic.jsonl` 的 8 个无空格中文/同义表达/硬负例，多数不使用 fact-type 过滤，避免只靠过滤获得高分。报告使用实际选择的 profile；真实模型尚未实测，不预填分数。完整在线 smoke 和跨栈验收仍属 Task 14。
