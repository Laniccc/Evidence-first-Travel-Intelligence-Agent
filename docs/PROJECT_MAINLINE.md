# Project Mainline

这份文档用于给当前仓库定主线：哪些路径是产品链路的一部分，哪些只是适配层、实验层或历史遗留。

## 当前主线

Evidence-first Travel Intelligence Agent 的核心目标是：回答旅游问题时，先拿证据，再写答案。LLM 负责理解、规划、裁剪和表达，但不能凭训练记忆直接编造事实。

> 架构重设方向：当前 S0-S10 是可运行主线，但后续应迁移到 Root Agent / Supervisor + Pipeline Gate + Tool Surface + Store 的 Agent Core。详见 [AGENT_CORE_REDESIGN_PLAN.md](AGENT_CORE_REDESIGN_PLAN.md)。

```text
User
  -> Web UI (optional)
  -> Java Gateway (optional)
  -> Python Agent
  -> State Machine
  -> Tools / MCP / Mock data
  -> Evidence
  -> Evidence aggregation
  -> Composer
  -> cited answer + trace
```

最小可运行主线是 Python Agent：

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

## S0-S10 状态链

| 阶段 | 主入口 | 产物 |
| --- | --- | --- |
| S0/S1 输入与上下文 | `TravelAgentStateMachine._build_conversation_context()` | `TravelAgentState`, `ConversationMemory` |
| S2 用户理解 | `LLMUnderstandingState` | `NormalizedUserRequest`, `SemanticFrame`, `TravelTask` |
| S3 回答模式路由 | `AnswerModeRouter`, `ResponseContractCompiler` | evidence / clarification / prior 等决策 |
| S4 区域与策略检查 | `TravelAgentStateMachine._apply_region_gate()` | 支持国家与城市判断 |
| S5 证据规划与工具调用 | `EvidencePlanningAndToolUseState` | 工具调用计划、MCP/subagent 结果、原始 evidence |
| S6 证据累积 | `EvidenceAccumulationState` | 合并后的 evidence 列表 |
| S7 证据聚合与 gap loop | `EvidenceAggregationState` | `EvidenceBrief`, `EvidenceDecisionReport`, gap requests |
| S8 答案合成 | `AnswerCompositionState` | `final_response` |
| S9 引用/限制检查 | `CitationChecker` | limitations, confidence |
| S10 响应输出 | `TravelAgentStateMachine._to_response()` | `TravelQueryResponse` |

## 数据和工具边界

- `packages/tools/registry.py` 是工具注册主入口。
- `packages/tools/mock/data.py` 是 mock 数据真相源。
- `packages/tools/mcp/` 是 MCP client、adapter、tool spec。
- `packages/tools/ticketing/`、`packages/tools/crawlers/`、`packages/tools/official_source/` 是垂直工具域。
- `apps/agent-python/app/tools/` 只保留兼容导出，不承载真实实现。

## 清理后的规则

- 不再新增 `tools/tools` 这种二级同名包。
- 不再新增 `schemas/schemas` 这种二级同名包。
- 不提交 `__pycache__`、`.pyc` 等运行缓存。
- 文档优先指向 `REPO_MAP.md`、`RUNBOOK.md` 和本文件，避免多份说明互相漂移。

## 判断新代码该放哪

| 需求 | 放置位置 |
| --- | --- |
| 新的事实来源 / 工具 | `packages/tools/` |
| 新的 Agent 状态或编排策略 | `apps/agent-python/app/orchestrator/` |
| 新的 LLM 子代理 | `apps/agent-python/app/agents/` |
| 新的响应或状态 schema | `apps/agent-python/app/schemas/` |
| 新的跨语言契约 | `contracts/schemas/` |
| 前端体验 | `apps/web/` |
| Java 网关或 session | `apps/api-java/` |
