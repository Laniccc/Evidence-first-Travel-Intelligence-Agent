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
| 合计 | 71 |

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

完整结果：[`apps/agent-python/evals/reports/final-offline.md`](../../apps/agent-python/evals/reports/final-offline.md) 和对应 JSON。

## BadCases 与诚实边界

当前确定性回归集没有失败 case。报告保留 `bad_cases` 字段；门禁失败会写入指标、实际值与阈值，供 CI 和面试演示定位。当前结果不等于线上泛化能力：fixture 与查询是受控的，deterministic hash embedding 不衡量中文语义质量，也没有覆盖高并发、真实网络抖动或跨语言召回。要声明真实 semantic lift，必须另跑 real-embedding profile、对抗改写集和线上观测数据。
