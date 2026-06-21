# LEGACY — `backend/` 冻结说明

> **状态**：Legacy（只读对照 / 紧急回退）  
> **生效**：自 Round 0 起  
> **新功能禁止写入本目录**

---

## 这是什么

`backend/` 是迁移前的 **FastAPI 单体入口**，包含：

- `app/main.py` — FastAPI 应用与 `/api/travel/*` 路由
- `app/orchestrator/`、`app/agents/` — Agent 状态机与编排
- `app/tools/` — 工具注册、Mock/Real/Hybrid、MCP
- `app/schemas/`、`app/config.py` 等 — 配置与领域模型
- `app/evals/` — 评测（尚未迁出）

当前仍可通过以下命令启动（**仅用于回退与对照**；**生产运行时请使用 `apps/agent-python`**）：

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## 允许做什么

| 操作 | 说明 |
|------|------|
| **运行 / 调试** | 验证旧行为、对比迁移前后结果 |
| **只读对照** | 查 import 路径、对照业务逻辑 |
| **紧急回退** | 新路径故障时临时切回 |
| **修 P0 阻断 bug** | 仅当 production 仍依赖本路径且无法回滚时；须同步修复 `apps/agent-python` |

---

## 禁止做什么

- **禁止新增功能**（新 Agent、新工具、新 API、新 schema 字段等）
- **禁止重构 / 大规模格式化**
- **禁止作为长期开发目标** — 新代码写入 monorepo 目标目录（见 `REPO_MAP.md`）

---

## 新代码应写到哪里

| 职责 | 目标目录 |
|------|----------|
| Python Agent 核心（orchestrator、agents、policies、prompts） | `apps/agent-python/` |
| Java API Gateway、session、周边服务 | `apps/api-java/` |
| 前端静态资源 | `apps/web/` |
| 跨语言 API 契约（JSON Schema / OpenAPI） | `contracts/` |
| 可复用 Python 包（tools、shared 等） | `packages/`（按 `MIGRATION_PLAN.md` 阶段迁入） |

---

## 与 monorepo 的关系

- `apps/agent-python/`、`packages/tools/` 等可能含有自 `backend/app` **复制**的副本；**以 `apps/agent-python` + `packages/tools` 为运行时真相源**。
- `apps/api-java` 通过 HTTP 代理至 `apps/agent-python` 的 `:8001` `/agent/query`。
- 迁移完成后，`backend/` 将仅保留薄 shim 或删除；详见 `MIGRATION_PLAN.md`。

---

## 相关文档

- [REPO_MAP.md](../REPO_MAP.md) — 目录职责地图
- [MIGRATION_PLAN.md](../MIGRATION_PLAN.md) — 分阶段迁移计划
