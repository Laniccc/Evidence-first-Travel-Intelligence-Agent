# Task 14 最终本地验收

日期：2026-09-04。分支：codex/resume-capability-closure。

## 交付范围

- Python 返回强类型、可选的 promotion_summary / index_sync_status，Java client、会话记录和 Web 展示贯通，旧响应仍可读取；safe_failure / failed 保持业务结果，不误报成传输故障。
- 区分候选拒绝、待审核、已发布但索引待同步、已索引、失败及未知。索引状态是交付时持久任务回执快照，不是持续刷新的服务探针；只读观测失败不能推翻已通过引用检查的回答。
- 新公共观测只含白名单状态及有界计数，不暴露原始 MCP payload、个人位置或凭据。内部运行审计可能包含来源及查询内容，仍需单独数据处理许可。
- CI 增加显式独立 stdio / 知识闭环测试与离线报告归档；报告携带 commit、dirty 标记、模型/SDK/Server 版本及数据集 SHA256。
- opt-in live smoke 使用真实生产装配，最多 4 次模型与 4 次地图调用；必须显式同意真实调用及临时数据处理，使用隔离临时数据库，结束清理，报告仅保留脱敏状态/计数/检查及版本信息。
- 更新运行手册、架构说明、能力矩阵和配置样例。锁文件仅更新 PostCSS / Nanoid 间接依赖以消除本轮安装检测的两项高危告警；重新安装审计为 0 告警。

## 本地验证结果

| 验证 | 结果 |
|---|---|
| Python 全量 pytest | 298 passed / 1 skipped / 1 warning |
| Java Maven tests | 28 tests，0 failures/errors/skipped |
| Web tests / production build | 4 passed / 成功 |
| 离线 all Eval | 112 cases，21 数值门禁及逐案例检查通过 |
| 真实 embedding retrieval | 28 cases，指标见下 |
| Docker Compose 配置展开 | 成功；未启动 Qdrant 服务 |
| 真实 LLM / 百度 smoke | not_run：未获得本轮调用与临时数据处理确认 |

Python 跳过项为真实 Qdrant server opt-in 集成测试；警告为 Starlette/httpx 弃用提示。CI 配置已更新但尚未推送触发，不能称远端 CI 通过。Java/Web 为契约、平台流程和构建测试，并非真实浏览器端到端线上验收。

真实 BAAI/bge-small-zh-v1.5：原 20 + 8 个自然中文/同义/硬负例，共 28 cases。Recall@3=0.9642857143、MRR=0.9714285714、nDCG@5=0.9781018860；metadata_filter_accuracy=1、provenance_completeness=1。

已知不足：semantic-wheelchair-natural（“上海博物馆坐轮椅方便进去吗”）目标 sm-access 排第 5，前四项为 sm-ticket、sm-reservation、sm-notice、sm-hours。未修改案例或放宽阈值掩盖该结果。小样本不代表线上泛化；本次仅独立测量真实 embedding retrieval，没有证明真实模型下的消融提升。

## 复现

在 apps/agent-python 使用项目 Python 环境：

```powershell
python -m pytest -q
python -m evals.runner --suite all --offline --fail-on-regression --report evals/reports/generated/resume-closure-offline.json
python -m evals.runner --suite retrieval --profile real-embedding --report evals/reports/generated/resume-closure-semantic.json
python -m evals.live_smoke --max-tool-calls 4 --max-llm-calls 4 --report evals/reports/generated/live-smoke.json
```

最后一条默认只记录 not_run，不读取凭据或调用服务。获得授权后按 RUNBOOK 增加两个 allow 开关；模型下载不可用时真实 embedding 报 blocked、不伪填指标。live smoke 单独使用 deterministic 本地索引，真实语义模型由 retrieval profile 独立验证，两者不混写。

分别在 apps/api-java 运行 mvn test，在 apps/web 运行 npm ci、npm test、npm run build；在仓库根运行 docker compose -f infra/qdrant/compose.yml config 与 git diff --check。

generated 报告为本地忽略产物，提交后可重跑以记录准确的干净 commit。保留已提交 final-offline 的旧 71-case 基线，不将旧文件冒充本轮报告。最终能力边界：实现及离线闭环完成、真实语义检索已测，真实 LLM/百度服务验收仍待授权；未合并或推送。
