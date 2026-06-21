# REPO_MAP — 当前仓库职责映射

> 基于根目录列表、`backend/app` 一层结构，及 `main.py` / `state_machine.py` / `registry.py` / `response.py` 的 import 关系整理。  
> **未做全仓库扫描**；子目录内部细节以目录名与顶层 import 推断，迁移前需按阶段逐包确认。

## 根目录（当前）

| 路径 | 职责 | 目标归属 |
|------|------|----------|
| `backend/` | Python 运行时：FastAPI、Agent 状态机、工具、配置、依赖 | 拆入 `apps/agent-python/` + `packages/*` |
| `docs/` | 项目文档 | `docs/`（保持） |
| `CLAUDE.md` | 仓库级 AI / 开发约定 | 根目录或 `docs/` |
| `README.md` / `RUNBOOK.md` | 说明与运维手册 | `docs/` 或根目录 |
| `.cursor/` | Cursor IDE 配置 | 根目录 |
| `*.ps1` / `upload_to_github.sh` | Git / 凭证脚本 | 根目录 `scripts/`（可选，非本轮） |
| `image.png` | 静态资源 | `apps/web/` 或 `docs/` |

**当前不存在**：`apps/`、`packages/`、`contracts/`、顶层 `tests/`。

---

## `backend/`（非 `app/`）

| 路径 | 职责 | 目标归属 |
|------|------|----------|
| `requirements.txt` | Python 依赖 | `apps/agent-python/` 或 workspace 根 `pyproject.toml` |
| `pytest.ini` | 测试配置 | `tests/` 或 `apps/agent-python/` |
| `.env` / `.env.example` | 运行时密钥与配置模板 | `apps/agent-python/`（不入库 secrets） |
| `.venv/` | 本地虚拟环境 | **不迁移**（gitignore） |

---

## `backend/app/` — 一层目录职责

### → `packages/agent_core/`（Agent 核心）

状态机、理解、路由、证据规划、合成等 **业务编排与 Agent 逻辑**。

| 路径 | 依据 |
|------|------|
| `orchestrator/` | `state_machine.py` 主流程；`TravelAgentStateMachine` 组装各 State |
| `agents/` | `state_machine.py` 引用 `IntentAgent`、`ComposerAgent`、`PlaceResearchAgent` 等 |
| `policies/` | 证据 / 状态策略（与 orchestrator 配套，命名惯例） |
| `prompts/` | LLM prompt 模板（与 agents / orchestrator 配套） |
| `catalog/` | `get_place_catalog()`，地点目录，被 state machine 使用 |
| `llm_client.py` | LLM 调用封装，被 orchestrator / tools 共用 |

### → `packages/tools/`（工具与 MCP）

工具注册、Mock/Real/Hybrid 实现、MCP 适配。

| 路径 | 依据 |
|------|------|
| `tools/`（整棵） | `registry.py`：`TravelToolRegistry`、`attach_mcp_tools`、各 `*_tool.py` |
| `tools/mcp/` | `registry.py` → `app.tools.mcp.registry_setup` |
| `tools/adapters/` | MCP 工具适配层（目录存在，与 mcp 同层） |
| `tools/real/` | 真实数据源工具实现 |
| `tools/capability_registry.py` | `state_machine.py` 引用 `CapabilityRegistry` |
| `tools/tool_router.py` | `state_machine.py` 引用 `ToolRouter` |

> `mock_data.py`（若存在于 `tools/` 内）属 **测试/开发数据**，最终归 `tests/` 或 `packages/tools` 的 dev fixtures，迁移阶段单独处理。

### → `packages/shared/`（跨层共享）

配置、通用 schema、工具类、存储等 **非编排、非 HTTP 入口** 的共用代码。

| 路径 | 依据 |
|------|------|
| `config.py` | `main.py`、`registry.py`、`state_machine.py` 均 `from app.config` |
| `schemas/`（部分） | 领域模型：`evidence`、`user_query`、`semantic_frame`、`tool_trace` 等，被 orchestrator / tools 引用 |
| `utils/` | 通用辅助（目录存在，典型 shared） |
| `storage/` | 持久化 / 缓存（目录存在，典型 shared） |
| `logging_config.py` | 日志上下文；`main.py` 使用，偏基础设施 |

### → `contracts/`（API 与对外契约）

HTTP 请求/响应、对外稳定的 DTO。

| 路径 | 依据 |
|------|------|
| `schemas/response.py` | `TravelQueryRequest` / `TravelQueryResponse` — `main.py` 的 `response_model` |
| `schemas/`（API 面子集） | 随 OpenAPI / 多语言客户端生成逐步抽出；其余 schema 暂留 `shared` 直至边界清晰 |

### → `apps/agent-python/`（Python API 壳）

FastAPI 应用入口、路由、中间件、依赖注入 **应用层**，不含核心编排实现。

| 路径 | 依据 |
|------|------|
| `main.py` | `FastAPI()`、`/health`、`/api/travel/*`、挂载 static、调用 `TravelAgentStateMachine` |

### → `apps/web/`（前端与静态资源）

| 路径 | 依据 |
|------|------|
| `static/` | `main.py`：`STATIC_DIR`、`StaticFiles`、`index.html` |

### → `tests/`（测试与 evals）

| 路径 | 依据 |
|------|------|
| `evals/` | 目录名即 eval / 回归测试套件（**本轮未读内容**） |
| `backend/pytest.ini` | 测试运行配置 |

### → `apps/api-java/`（占位，当前无代码）

仓库现状为 **Python FastAPI 单体**；目标 monorepo 预留 Java API，与 `agent-python` 并列，**本轮无对应目录**。

---

## 依赖关系（从已读文件推断）

```
main.py
  ├── config, logging_config          [shared / app shell]
  ├── schemas.response                [contracts]
  └── orchestrator.state_machine      [agent_core]
        ├── agents/*                  [agent_core]
        ├── orchestrator/*            [agent_core]
        ├── catalog, llm_client       [agent_core / shared]
        ├── schemas/*                 [shared / contracts]
        └── tools.*                   [tools]
              └── tools.mcp.*         [tools / mcp]
```

---

## 迁移时注意（仅记录，本轮不执行）

1. **Import 前缀**：当前统一为 `app.*`；拆包后需分阶段改为 `agent_core.*` / `tools.*` / `shared.*` 等，并保留临时 shim。
2. **`config.py` 与 `schemas/`**：被多层引用，宜在 `shared` + `contracts` 阶段先定边界再动 `agent_core`。
3. **`evals/`**：位于 `backend/app/evals/`，与生产代码混放；目标迁至顶层 `tests/`。
4. **静态站与 API**：`main.py` 同时承担 API 与 static；拆 `apps/web` 时需拆路由或反向代理。

---

## 未在本轮确认的内容

以下目录 **仅记录名称**，内部文件列表未扫描，迁移该包前需单独开阶段读取：

- `agents/`、`orchestrator/states/`、`tools/` 子树、`policies/`、`prompts/`、`storage/`、`utils/`、`evals/` 内部
