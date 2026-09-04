# 批次 C 验证与交接

日期：2026-09-04。范围：Task 7–10。分支：codex/resume-capability-closure。
executing-plans 检查点：11/15 tasks 完成；停止在批次 C，不执行 D，不推送或合并。

## Task 7：候选提取与五层校验

- 新 CandidateExtractor 使用独立系统提示，只传 allowlisted 字段、景点 ID 和 evidence/call ID。最多 4 个候选、一次 schema repair，整个提取阶段默认 8 秒。
- 模型不提供 URL、来源类型、权限、哈希、有效期或发布状态。依次验证 Schema、精确 Grounding、Provenance、Temporal、Persistence Policy。
- 仅 address → general_description 可按明确留存许可自动发布；shop_hours → opening_hours 进入 pending/manual review，不升级为官方来源。
- 来源固定 structured；来源 URL、provider/UID/source_id、payload hash、知识 TTL 由代码生成/核验。
- 默认禁止持久晋升；生产 handler 在权限关闭时不调用候选模型。临时证据仍可服务本次请求。
- 反例覆盖额外 authority 字段、跨景点、改写引用、缺引用、不允许事实、源数据哈希篡改、UID 不符、未来/过期快照、TTL 超界、指令污染、超过四个候选、模型传输失败。
- 校验采用规范化后原文相等，不声称通用语义蕴含或完备的提示注入检测。

## Task 8：不可变版本与迁移

- v2 canonical hash 覆盖来源绑定、来源类型/URL/title、正文、顺序事实块及 valid_from/to；payload_hash 单独保留。
- 同文不同 chunks/TTL/来源元数据会产生新版本；相同版本重复 ingest/publish 幂等。
- 仅 pending 能发布，active 重复发布不修改时间；superseded/rejected/expired 不可重新激活，已到期 pending 禁止发布。
- source_id 不允许换绑景点；每个版本保存来源元数据快照，不让后续 source 修改重写历史证据。
- 自动 chunk ID 含版本身份。首次导入显式 fixture ID 保留兼容；后续同名 ID 改用版本限定 ID，原引用不变。
- 迁移在事务中保留历史行、旧 hash_version=1、FTS 及外键；新版本 hash_version=2。移除 attraction+URL 唯一约束，允许同 POI 不同 fact_type 的独立 source_id。
- 迁移重复运行安全，连接明确关闭。历史 fixture 通过注入历史发布时钟构造，而不是放开生产过期发布规则。

## Task 9：同库事务与索引任务

- PromotionService 在同一 knowledge SQLite 事务中保存 decision、ingest、publish 与 index_sync_job。验证在拿到写锁后执行，避免等待锁期间时间条件失效。
- 注入“已 publish、未 enqueue”故障，确认知识、FTS、decision、job 全部回滚。
- outbox 按 version 去重；单实例一次处理一个任务，5 分钟 lease、attempt CAS，最多 3 次尝试，10/20 秒退避后重试，耗尽后 failed。
- 发布后 Qdrant 不可用：SQLite active 保留，job pending，可由重启 coordinator 或 sync-pending CLI 恢复。
- IndexSynchronizer 从一次 SQLite 查询快照构建，切换 generation 时持写锁重新比对 corpus digest；语料漂移拒绝切换并留下失败原因。
- 同进程 rebuild 串行；生产索引维护与 dense 检索共用 BoundedIO 的 dense lane，避免并发操作 Qdrant local。
- 复用已有 generation 前核对实际数量及每个点的 ID/version/hash 等元数据；损坏点重新写入，只清理当前重建 namespace 的孤立点，不删除其他 generation。
- 旧 generation 清理失败保留已成功的新 generation，并记录 cleanup_failure_code；修复同 corpus/model 时不得删掉共享 point ID。
- CLI 示例（apps/agent-python）：

```powershell
./.venv-batch-b/Scripts/python.exe -m app.evidence.knowledge.cli sync-pending --db ./data/knowledge.sqlite3 --limit 10
```

还有 pending/running/failed job 时 CLI 返回非零。默认连接本地 Qdrant，支持与 reindex 相同的显式连接/embedding 参数。

## Task 10：生产入口和逐状态审计

- build_runtime 实际装配 SingleAttemptLLMClient → PrimaryUnderstandingAdapter；BaiduGapTool 使用目录中的可信景点名称/城市绑定，不让模型注册新景点。
- FastAPI lifespan 启动/关闭 SDK MCP owner、模型客户端、索引 coordinator、受控线程和 Qdrant。关闭验证包括 stdio PID 退出、各 lane 清空及 Qdrant 本地目录锁释放。
- 新状态链为 Evidence Evaluate → Knowledge Promote（至多一次）→ 预先确定的 Compose 或安全出口；不存在 promote → gap 边。
- 移除旧 pending_writer 旁路。晋升失败/提取失败/留存关闭均保留 transient，记录 recovered + 原因码，不伪造发布成功。
- SQLite 工作线程超时不等于取消写入：报告 promotion_persistence_unknown、不重试，实际任务结束后释放容量；durable decision/job 保持 run/query/trace 关联。
- 未提供 Trace ID 时由服务入口生成并贯穿状态/完成日志；恢复事件的 failure_code 同时写入 phase_event、execution_attempt 和日志。
- readiness 区分 disabled / configured / credentials_missing / configuration_missing / unavailable；configured 仅表示模型配置就绪，不等同于真实服务已验证。
- MCP 可选启动失败降级；Qdrant readiness 由专用 lane 刷新状态，避免健康探针并发访问 local client。
- offline 模式禁止模型/MCP/coordinator，且拒绝 server Qdrant 或 FastEmbed 配置，避免离线入口偷偷联网/下载。

### 新配置（默认安全关闭）

- AGENT_RUNTIME_PROFILE=offline（默认）或 online。
- BOUNDED_BAIDU_ENABLED=false；管理员配置 BOUNDED_BAIDU_NODE 和可选 BOUNDED_BAIDU_SERVER_ENTRYPOINT。默认 entrypoint 指向 infra/baidu-mcp 的固定安装包，不执行 npx/latest。
- KNOWLEDGE_PROMOTION_ENABLED=false；BAIDU_STORAGE_PERMITTED=false。真实数据权限未确认，不能因为软件包许可而开启后者。
- INDEX_JOB_POLL_SECONDS=5；测试使用 0.05 秒。使用既有模型凭据及 BAIDU_MAP_AK，将后者映射给官方 Server 的 BAIDU_MAP_API_KEY。
- 旧广域 MCP 开关不控制这条新链。未增加已移除能力。

## 验证结果

```powershell
# apps/agent-python
./.venv-batch-b/Scripts/python.exe -m pytest -q
./.venv-batch-b/Scripts/python.exe -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/generated/batch-c-final.json
```

- 批次前：219 passed / 1 skipped；批次后：256 passed / 1 skipped，1 个既有 Starlette/httpx 弃用警告。
- 新增候选、版本、事务/恢复、生产入口测试合计 37 个参数化案例；真实 stdio 测试子进程和持久 Qdrant local，模型为假 HTTP transport。
- 原 71 个 Eval 案例和 13 个门禁全部通过，阈值/预期未降低。版本故障 suite 结束清理其注入的无效向量，避免污染健康索引复用 suite；损坏索引恢复另有独立测试。
- Recall@3/MRR/NDCG@5/metadata_filter_accuracy/state_path_accuracy/stale_vector_rejection/index_rebuild_consistency/citation_precision/abstention_precision/replay_consistency 为 1.0；non_active_leakage_rate、illegal_transitions、unsupported_hard_facts 为 0。
- 这些仍是受控 hash-embedding 离线结果，不能写成真实语义质量指标。报告保存在 ignored generated 目录，未覆盖已提交基线。
- 公共 Java-Python DTO 和 Web UI 未改，本批未跑 Java/Web；原根目录的个人流程图未改动或提交。

## 限制与下一批

- 尚未调用真实 LLM/百度 Server，没有真实服务 smoke 或 real embedding 质量验收。
- 单实例 durable coordinator，不是多节点 HA；底层同步调用不能强杀，永久阻塞仍可拖延 shutdown。
- knowledge promotion 开关治理知识入库；运行审计仍保存必要的脱敏 transient 产物。真实上线前需同时确认运行审计的保留许可/周期，不能把入库关闭等同于完全不留任何数据。
- 暂未将新的晋升/协议测试并入 Eval 发布门禁。完整 Miss → Promote → 后续 dense-only Hit 的发布级回归属于 Task 13。
- 批次 D：Task 11 Citation 严格支持关系与终态失败审计；Task 12 transient 无副作用 Replay；Task 13 新案例/硬门禁；Task 14 Java/Web、文档和有凭据/权限/预算时的真实验收。
- 本批没有新增自由生成答案模型，Compose 继续使用确定性输出。简历中的完整可靠性与回放表述仍需等待 D。
