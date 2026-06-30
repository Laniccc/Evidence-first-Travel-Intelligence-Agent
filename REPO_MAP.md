# REPO_MAP - 当前仓库职责映射

本仓库的主线是：用户问题进入 Python Agent，经意图理解、证据规划、工具取证、证据裁剪和答案合成后返回；Web 和 Java 只负责入口体验与网关，不承载事实判断。

## 一条主线

```text
apps/web
  -> apps/api-java
    -> apps/agent-python/app/main.py
      -> app/orchestrator/state_machine.py
        -> S2 LLMUnderstandingState
        -> S3 AnswerModeRouter + ResponseContractCompiler
        -> S5 EvidencePlanningAndToolUseState
        -> S7 EvidenceAggregationState
        -> S8 AnswerCompositionState
      -> packages/tools
        -> Evidence[]
```

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `apps/agent-python/` | Python Agent 核心。FastAPI 入口、状态机、agents、orchestrator、schemas、evals。 |
| `packages/tools/` | 工具真实实现与注册中心。所有工具输出都必须归一为 `Evidence`。 |
| `apps/api-java/` | Java API Gateway 与 session 记忆层，转发到 Python Agent。 |
| `apps/web/` | 前端 SPA，只负责交互和展示。 |
| `contracts/` | 跨语言 JSON Schema 契约。 |
| `docs/` | 设计、运行和阶段性方案文档。 |
| `scripts/` | 启动、验证和 smoke 脚本。 |
| `external/` | 外部 crawler adapter / runner，不作为 Agent 主逻辑入口。 |

## Python Agent 主路径

| 阶段 | 文件 | 说明 |
| --- | --- | --- |
| API 入口 | `apps/agent-python/app/main.py` | `/agent/query` 调用 `TravelAgentStateMachine.run()`。 |
| 状态机 | `apps/agent-python/app/orchestrator/state_machine.py` | S0-S10 的主调度。 |
| 理解 | `apps/agent-python/app/orchestrator/states/llm_understanding_state.py` | 用户问题 -> `NormalizedUserRequest` / `SemanticFrame` / `TravelTask`。 |
| 路由 | `apps/agent-python/app/orchestrator/answer_mode_router.py` | 判断 clarification、model prior、evidence required 等模式。 |
| 取证 | `apps/agent-python/app/orchestrator/states/evidence_planning_and_tool_use_state.py` | 按白名单和策略调用工具 / MCP / subagent。 |
| 证据裁剪 | `apps/agent-python/app/orchestrator/states/evidence_aggregation_state.py` | 将候选证据聚合为可用于作答的 evidence brief / decision report。 |
| 答案合成 | `apps/agent-python/app/orchestrator/states/answer_composition_state.py` | Composer 只基于 evidence 输出最终回答。 |
| 工具注册 | `packages/tools/registry.py` | Mock / real / hybrid / MCP / ticketing / crawler 工具入口。 |
| mock 真相源 | `packages/tools/mock/data.py` | 首期 mock 数据的唯一真相源。 |

## 保留的兼容边界

- `apps/agent-python/app/tools/*` 是 Agent 内部兼容导出层，转发到根包 `tools.*`。
- `packages/tools/*` 是工具实现主目录，新增工具应放在这里或其子包中。
- `apps/agent-python/app/schemas/*` 是 Agent schema 主目录，新增 schema 应放在这里。

## 不再使用的历史路径

以下影子目录已清理，不要重新添加：

- `packages/tools/tools/`
- `apps/agent-python/app/tools/tools/`
- `apps/agent-python/app/schemas/schemas/`

这些目录来自早期迁移/复制，外部没有有效引用，会让真实实现位置变得不清晰。

## 开发约定

1. 新工具必须返回 `Evidence` 对象，Composer 只能基于 evidence 总结。
2. 首期只支持 Japan / China / South Korea。
3. 工具真实实现优先放在 `packages/tools/`，Agent 侧通过 `app.tools` 兼容层引用。
4. 状态链改动优先看 `state_machine.py` 和 `app/orchestrator/states/`。
5. 调试最近一次问答看 `apps/agent-python/debug_last_session.md`。
