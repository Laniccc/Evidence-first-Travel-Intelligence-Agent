# 批次 A 验证与交接

日期：2026-09-04。范围：实施计划 Task 0–3。分支：codex/resume-capability-closure。
按 executing-plans 执行红测 → 实现 → 相关回归 → 批次检查点；本批结束不进入 B，不合并、不推送。

## 完成内容

1. 基线与事实矩阵：修正 AGENTS.md 的 scope gate 路径，保留原测试/评测阈值和数据集。
2. TaskRequest / KnowledgeCandidate / GroundingRef / McpEvidenceEnvelope：
   严格额外字段限制、事实枚举、时区时间、不可变来源封装；模型不能赋予知识发布权或来源权威性。
   TransientEvidence 保留旧构造兼容，新的 from_verified_payload 入口校验必需来源字段、有效期与正文 hash。
3. PrimaryUnderstandingAdapter：
   单次原生异步模型调用，SDK max_retries=0；UnderstandingHandler 独占一次 schema repair 预算，
   两次模型调用共用 deadline。鉴权、限流、超时、连接故障不触发 schema repair。
   模型成功/repair/规则回退/澄清路径分别记录，保留安全错误码与模型/提示词/Schema 版本摘要。
   取消向上传播；修复和降级不记录 provider 错误正文或完整 prompt。
4. Retrieval Plan：
   保存原问题、dense 用的重写问题、独立 lexical query、用户约束、UTC as_of；
   请求 timezone 默认 Asia/Shanghai；明确日期不被当前时间覆盖。
   无年份/不明确时间、非法日期、DST 歧义均澄清；规则路径能识别有限 ISO/中文日期及今天/明天/后天/昨天。
   Top-K 由配置传入且上限 5，实体 ID/子任务 ID 由代码生成；同一 ID 的别名不能伪装成双景点比较。
   SQLite 和 dense 后过滤均要求指定非当前时间的明确有效区间；无时间区间的当前 transient snapshot 不用于推断历史/未来。

## 测试证据

所有 Python 命令执行目录：apps/agent-python。生成的 JSON 报告位于 ignored generated 目录，不覆盖仓库既有评测报告。

| 检查 | 结果 |
|---|---|
| 执行前 python -m pytest -q | 127 passed / 1 skipped |
| Task 0 scope gate | 3 passed |
| Task 1 新契约测试 | 26 passed（首次运行模块缺失红测） |
| Task 1 states + knowledge + scope 回归 | 76 passed |
| Task 2 理解与原路由测试 | 20 passed（首次运行新 client 缺失红测） |
| Task 2 修正分层后全量回归 | 166 passed / 1 skipped |
| Task 3 日期/中文检索/真实 composition root 检查 | 25 passed（首次模块缺失；追加测试先复现 Top-K 未传入、快照越界与相对日期误解析，再修复） |
| 批次结束 python -m pytest -q | 188 passed / 1 skipped |
| retrieval suite（20 原有案例） | Recall@3=1、MRR=1、NDCG@5=1、metadata_filter_accuracy=1、provenance_completeness=1 |
| 原 all suite（71 个受控案例） | 13 项门禁全部通过，未调低阈值 |

复现命令：

```powershell
python -m pytest -q
python -m evals.runner --suite retrieval --offline --fail-on-regression --report evals/reports/generated/batch-a-retrieval.json
python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/generated/batch-a-final.json
```

保留项：真实 Qdrant server 测试为 opt-in skipped；原 Starlette/httpx 弃用警告仍存在。
本地 composition root 测试使用临时目录的真实 SQLite/FTS5 与 Qdrant local，dense 尚未建索引时验证 lexical_only 降级；不冒充真实 dense 语义验收。

## 为守住现有架构所作的小范围调整

- 全量回归发现 understanding → evidence 和 integrations → governance 跨层导入违规。
  将唯一 FactType 定义放到 contracts，原 knowledge.models 继续重导出；LLM transport 只返回白名单错误码，由 orchestration 映射运行失败类型。架构测试未修改。
- UserConstraints 放入共享内部 contracts，避免 evidence 反向依赖 understanding；Java-Python 请求/响应字段未改动。
- Task 3 必须小幅修改 lexical、reranker、report、claim_decision 和 main/state_machine 才能把日期/预算落实到交付，而非只添加未使用字段。
- 新增 Windows tzdata 安装声明，支持没有系统 IANA 时区库的干净 Windows Python；当前测试环境已有可用时区库，未执行新环境重装。

## 不能宣称已完成的部分

- LLM adapter 未注入生产入口；offline/online 配置只是后续 Task 10 的声明，尚未实施完整 profile readiness/生命周期管理。
- MCP SDK stdio、百度真实接入、候选 grounding、晋升/索引待办、完整 Citation Guard 与 MCP Replay 未实施。
- 评测仍为原受控 offline/hash-embedding 门禁。新增测试证明边界行为，不代表真实模型或真实 RAG 指标。
- 日期解析刻意保守，不覆盖全部自然语言时间表达；lexical 用有限词表和 FTS 前缀，不是通用中文分词系统。
- 当前快照默认不能用于历史/未来指定时间回答；后续 MCP 接线不能放松这一限制来提高覆盖率。

下一批 B：Task 4–6（并行检索、标准 MCP 会话、百度 search/detail → Transient Evidence）。
