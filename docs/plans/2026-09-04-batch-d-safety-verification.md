# 批次 D 安全与 Eval 检查点（Task 11–13）

日期：2026-09-04。分支：codex/resume-capability-closure。

这是 Task 11–13 的检查点，不是 Task 14 或整个项目的完成声明。沿用 executing-plans 的红测、实现、回归和检查点流程。

## 已完成

- Task 11：硬事实必须对应 Evidence Evaluate 已批准的 claim/value/evidence 组合；复核景点、子任务、fact、时间、真实 transient hash 与持久版本。拒绝“门票免费”引用“六十元”、跨景点引用和夹带事实的建议。Delivery 投影失败写入 typed failure；审计不可用不返回伪成功。
- Task 12：完整 delivery snapshot 保存原时间、检索、MCP 临时证据、晋升、规则与配置版本、回答和引用决策；digest 防止损坏。Replay 只复制原产物并产生新的审计 run，不重新执行外部调用或知识写入。不完整的历史 run 明确拒绝。
- Task 13：原 71 个案例全部保留；新增理解 8、MCP 8、晋升 16、grounding 8，以及 1 个真实生产装配闭环，共 112。原 13 门禁保持阈值，新增 8 门禁；业务逐案例失败也阻止发布，BadCase 可定位到 case/state/failure/artifact。
- 闭环使用真实 build_runtime、假 HTTP 模型响应、独立 stdio 假服务进程、本地持久 SQLite/Qdrant。首次地址缺失→2 次地图工具调用→active 晋升；注入向量写入故障→durable job pending→恢复同步；禁用 lexical 且禁止再调 MCP 后，第二次仅 dense 命中第一次晋升的版本。重复晋升复用 version/job。
- Replay 的模型、MCP、发布、索引方法设置失败探针；检查 document_version/index_sync_job/promotion_decision 数量不增加。报告保留实际中间产物，而不是仅保留已删除临时数据库的引用。
- 拆分不截断的检索安全过滤与最终排序；四组消融统一候选上限，不再绕过 top_k ≤ 5。real-embedding 额外 8 个自然中文、同义改写和硬负例已准备；尚未实际运行真实 embedding 模型。

## 回归中发现并修复的问题

1. 原多轮案例 multi-pronoun-suitability 的实际结果是 clarification，但原 13 汇总门禁未覆盖它。新增逐案例门禁后识别该错误：Java/session 快照中的地点是字符串或序列化对象，旧规则期待 typed PlaceContext。现在在规则边界重新绑定已知景点。原案例预期未改，四个 conversation 案例通过。
2. SQLiteRunStore 原来使用 connection 的事务上下文，但未关闭连接，Windows 下临时审计库被占用。改为事务结束必定关闭；新增关闭、异常回滚回归测试，不忽略清理错误。
3. Task 11 旧 citation fixture 的文本原为“故宫开放时间声明”（并非证据内事实），改用既有 fixture 的“八点三十分开放”。未改 expected supported/abstain、原数据集或数值门槛。
4. Task 12 旧 Replay 测试仅写检索中间产物；测试现在先完成原评估、组合、Guard 和快照，再重放。生产不会把未完成的历史 run 补造为完成状态。

## 验证

工作目录 apps/agent-python，使用本地 .venv-batch-b/Scripts/python.exe：

```powershell
.venv-batch-b/Scripts/python.exe -m pytest -q
.venv-batch-b/Scripts/python.exe -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/generated/batch-d-task13.json
```

- Python：282 passed / 1 skipped / 1 warning。跳过为既有真实 Qdrant opt-in；警告为既有 Starlette/httpx 弃用提示。
- Eval：exit 0；112 cases；21 数值门禁 + 逐案例门禁通过；BadCases=0。
- 原 Recall@3 / MRR / nDCG@5 = 1.0，来源于原 20 个受控 hash-embedding 检索案例，不能写成真实语义准确率。
- unsafe_auto_publish=0、provenance_fabrication=0、mcp_budget_violations=0。
- promotion_idempotency=1、sync_recovery=1、miss_promote_dense_hit=1。
- replay_external_calls=0、replay_write_side_effects=0。
- 14 个不合规知识候选被拒绝；8 个 adversarial claims 被移除；不能把这些安全拒绝计作“已交付无依据事实”。
- tests/evals/test_release_gate_failures.py：逐案例 unsafe publish、越预算、错误引用/不支持工具的观测触发失败；修改一个数据集预期并真实调用 all CLI，返回 1 且报告 promotion-stable-address。旧 conflict/recovery/conversation 失败、案例缺失与检索 provenance 缺失也阻止发布。
- git diff --check：通过。生成报告在 ignored 的 generated 目录，未覆盖已提交历史 71-case 报告。

## 尚未完成 / 不作声明

Task 14 尚未开始：Java/Python/Web 可选 promotion/index 观测契约、展示、CI、完整项目文档、Maven/Web/build/compose 总体验收、真实 embedding 和实际 LLM/百度 smoke。

本次没有读取真实 key/AK，没有访问真实模型或百度数据服务，没有模型下载；因此真实接入与语义效果状态仍为 not_run，而不是 pass。真实 smoke 需要用户的凭据、联网/费用及数据留存政策授权。

Task 11 提交：6917cd2；Task 12 提交：c33aed7；Task 13 为本记录所在提交。未推送、未合并；根目录个人图片未触碰。
