# REPO_MAP — 当前仓库职责映射

> Monorepo 目标目录为**唯一开发入口**；`backend/` 已标记 **LEGACY**（见 [backend/LEGACY.md](backend/LEGACY.md)）。  
> `backend/app` 一层结构仅作对照参考；**新功能不得写入 `backend/`**。

## 根目录（当前）

| 路径 | 职责 | 状态 |
|------|------|------|
| `apps/agent-python/` | **Python Agent 核心**（orchestrator、agents、FastAPI 入口） | 目标主路径（迁移中） |
| `apps/api-java/` | **Java API Gateway** / session / 周边服务 | 目标主路径（:8080 → Python） |
| `apps/web/` | **前端**（静态 `dist/`） | 目标主路径 |
| `contracts/` | **跨语言协议**（JSON Schema 等） | 目标主路径 |
| `packages/` | 可复用 Python 包（tools、shared、agent_core） | 迁移中 |
| `backend/` | 旧 FastAPI 单体 | **LEGACY** — 回退与对照 only |
| `docs/` | 项目文档 | 保持 |
| `REPO_MAP.md` / `MIGRATION_PLAN.md` | 重构地图与计划 | 根目录 |

---

## Monorepo 应用层（`apps/`）

| 路径 | 职责 | 说明 |
|------|------|------|
| `apps/agent-python/` | Python Agent 核心 | 状态机、agents、policies、prompts；未来 `uvicorn` 主入口 |
| `apps/api-java/` | Java API Gateway | HTTP 代理、session、周边服务；对接 `contracts/` |
| `apps/web/` | 前端 | `dist/` 静态资源；UI 与 API 分离 |

---

## 契约层（`contracts/`）

| 路径 | 职责 |
|------|------|
| `contracts/json-schema/` | `TravelQueryRequest` / `TravelQueryResponse` 等跨语言 DTO |

Java 与 Python 均应以 `contracts/` 为对外协议真相源，而非各自手写 DTO。

---

## 可复用包（`packages/`）

| 路径 | 职责 | 状态 |
|------|------|------|
| `packages/tools/` | 工具注册、MCP、Mock/Real/Hybrid | 副本存在，待切换 import |
| `packages/agent_core/` | orchestrator、agents 等 | 待创建 / 迁入 |
| `packages/shared/` | config、schemas、utils、storage | 待创建 / 迁入 |

---

## LEGACY：`backend/`

> 详见 **[backend/LEGACY.md](backend/LEGACY.md)**。禁止新功能；仅运行、对照、紧急回退。

| 路径 | 原职责 | 迁移目标 |
|------|--------|----------|
| `backend/app/main.py` | FastAPI + `/api/travel/*` | `apps/agent-python/` |
| `backend/app/orchestrator/` | 状态机 | `apps/agent-python/` |
| `backend/app/agents/` | Agent 实现 | `apps/agent-python/` |
| `backend/app/tools/` | 工具与 MCP | `packages/tools/` |
| `backend/app/schemas/` | 领域 + API 模型 | `packages/shared/` + `contracts/` |
| `backend/app/config.py` | 配置 | `packages/shared/` 或 `apps/agent-python/` |
| `backend/app/evals/` | 评测 | `tests/evals/` |
| `backend/requirements.txt` | Python 依赖 | `apps/agent-python/` |

`backend/app/` 一层（对照用）：`agents`、`catalog`、`config.py`、`evals`、`llm_client.py`、`logging_config.py`、`main.py`、`orchestrator`、`policies`、`prompts`、`schemas`、`storage`、`tools`、`utils`。

---

## 目标依赖关系

```
客户端
  → apps/api-java (:8080)     [Gateway / session / 周边]
       → HTTP → apps/agent-python (:8000)   [Python Agent 核心]
            → packages/tools
            → packages/shared
  → apps/web                  [前端，独立部署或 CDN]

contracts/json-schema  ◄──  apps/api-java
                      ◄──  apps/agent-python

backend/  (LEGACY，回退对照，不再新增代码)
```

---

## 迁移注意

1. **新功能只写目标目录**；`backend/` 仅修 P0 阻断 bug 且须同步到 `apps/agent-python`。
2. **Import 前缀**仍为 `app.*`（legacy）；切换后改为包名 + shim。
3. **双份副本**（如 `packages/tools`）切换前勿只改一处。

---

## 未在本轮扫描的内容

`backend/app` 子树内部、`apps/*` 与 `packages/*` 内部文件列表未展开；需要时按阶段向用户索要路径。
