# MIGRATION_PLAN — Monorepo 分阶段迁移计划

> **原则**：每轮只做一个阶段；机械迁移优先（`mkdir` / `git mv` / import 批量替换 / 单阶段测试）。  
> **禁止**：全仓库扫描、同轮同时改 agent / api / web / tools / tests。

## 目标结构

```
Evidence-first Travel Intelligence Agent/
├── apps/
│   ├── agent-python/      # FastAPI 入口、路由、中间件、应用配置
│   ├── api-java/            # Java API（占位，后期）
│   └── web/                 # 静态前端（index.html、assets）
├── packages/
│   ├── agent_core/          # orchestrator、agents、policies、prompts、catalog
│   ├── tools/               # ToolRegistry、MCP、mock/real/hybrid 工具
│   └── shared/              # config、logging、utils、storage、领域 schemas
├── contracts/               # TravelQueryRequest/Response、OpenAPI 产物
├── docs/                    # 文档（自现有 docs/ 整理）
├── tests/                   # evals、集成测试、pytest 配置
├── REPO_MAP.md
├── MIGRATION_PLAN.md
└── .cursor/rules/repo-scope.mdc
```

---

## 阶段总览

| 阶段 | 名称 | 产出 | 是否动 import |
|------|------|------|----------------|
| **P0** | 重构准备 | 本文档、`REPO_MAP.md`、Cursor 规则 | 否 |
| **P1** | 骨架目录 | 空目录 + `.gitkeep` + 根 `README` 指针 | 否 |
| **P2** | `packages/shared` | 抽出 config、logging、utils、storage、通用 schemas | 是（仅 shared 相关） |
| **P3** | `packages/tools` | 整棵 `tools/` 迁入 | 是（仅 tools 相关） |
| **P4** | `packages/agent_core` | orchestrator、agents、policies、prompts、catalog、llm_client | 是（仅 agent_core 相关） |
| **P5** | `apps/agent-python` | `main.py`、应用级 wiring、`.env.example` | 是（app 入口层） |
| **P6** | `apps/web` | `static/` 迁出；API 改静态路径或代理 | 是（main + static 引用） |
| **P7** | `tests/` | `evals/` → `tests/evals/`；`pytest.ini` 调整 | 是（测试 import） |
| **P8** | `contracts/` | API DTO、OpenAPI 生成物 | 是（contracts 边界） |
| **P9** | 收尾 | 删除 `backend/` 空壳、更新 RUNBOOK、workspace 元数据 | 是（文档与路径） |

**每阶段之间**：必须验收通过再进入下一阶段。

---

## P0 — 重构准备（本轮）

### 允许读取
- 根目录列表
- `backend/app/` 一层结构
- `backend/app/main.py`
- `backend/app/orchestrator/state_machine.py`
- `backend/app/tools/registry.py`
- `backend/app/schemas/response.py`

### 允许修改
- `REPO_MAP.md`（新建）
- `MIGRATION_PLAN.md`（新建）
- `.cursor/rules/repo-scope.mdc`（新建）

### 禁止触碰
- `backend/app/**` 源码
- `docs/`、`README.md`、`RUNBOOK.md`（除非用户明确要求）
- `evals/`、`static/`、mock data

### 验收
```bash
# 仅确认文件存在，无代码变更
test -f REPO_MAP.md && test -f MIGRATION_PLAN.md && test -f .cursor/rules/repo-scope.mdc
```

---

## P1 — 骨架目录

### 目标
创建目标 monorepo 空目录树，**不移动任何 Python 代码**。

### 允许读取
- 根目录列表
- `REPO_MAP.md`、`MIGRATION_PLAN.md`

### 允许修改（≤20 文件）
- `apps/agent-python/.gitkeep`
- `apps/api-java/.gitkeep`
- `apps/web/.gitkeep`
- `packages/agent_core/.gitkeep`
- `packages/tools/.gitkeep`
- `packages/shared/.gitkeep`
- `contracts/.gitkeep`
- `tests/.gitkeep`
- 可选：根目录 `pyproject.toml` 或 `Makefile` 占位（**不含业务代码**）

### 禁止触碰
- `backend/**` 内一切 `.py`
- import、requirements 实质性变更

### 验收
```bash
ls apps/agent-python apps/web packages/agent_core packages/tools packages/shared contracts tests
```

---

## P2 — `packages/shared`

### 目标
迁出：`config.py`、`logging_config.py`、`utils/`、`storage/`、非 API 的 `schemas/*`（边界以 `REPO_MAP.md` 为准）。

### 允许读取（≤12 个源码文件/轮）
- `backend/app/config.py`
- `backend/app/logging_config.py`
- `backend/app/utils/`（逐文件，按用户指定或每轮 ≤12）
- `backend/app/storage/`（同上）
- `backend/app/schemas/`（除 `response.py` 可先不动）
- 直接 import 上述模块的文件（由用户列出或每轮指定）

### 允许修改
- `packages/shared/**`（新建）
- `backend/app/**` 内 **仅** shared 相关 import 与 shim（`app.config` → `shared.config` 或兼容层）
- `backend/requirements.txt` 或新 `packages/shared/pyproject.toml`

### 禁止触碰（同轮）
- `orchestrator/`、`agents/`、`tools/`、`main.py`、`evals/`、`static/`

### 验收
```bash
cd backend
python -c "from app.config import get_settings; get_settings()"
pytest app/evals/ -q --ignore=app/evals/integration -x  # 或用户指定的最小冒烟集
```

---

## P3 — `packages/tools`

### 目标
`backend/app/tools/` 整树迁入 `packages/tools/`；MCP 配置路径更新。

### 允许读取（≤12/轮）
- `backend/app/tools/registry.py`
- `backend/app/tools/mcp/*.py`
- `backend/app/tools/adapters/*.py`
- 用户指定的单个 `*_tool.py`
- `state_machine.py`（仅 tools import 相关行）

### 允许修改
- `packages/tools/**`
- tools 相关 import（`app.tools` → `tools`）
- **禁止同轮**改 `orchestrator/` 业务逻辑（仅 import 路径）

### 禁止触碰（同轮）
- `agents/`、`main.py`、`evals/`、`static/`

### 验收
```bash
cd backend
python -c "from app.tools.registry import TravelToolRegistry; TravelToolRegistry()"
pytest app/evals/tool_trace_tests.py app/evals/mcp_evidence_planning_tests.py -q -x 2>/dev/null || pytest app/evals/ -k tool -q -x
```

---

## P4 — `packages/agent_core`

### 目标
迁出：`orchestrator/`、`agents/`、`policies/`、`prompts/`、`catalog/`、`llm_client.py`。

### 允许读取（≤12/轮）
- `state_machine.py` 及用户指定的单个 state / agent 文件
- 该轮涉及的 import 源文件 only

### 允许修改
- `packages/agent_core/**`
- agent_core 相关 import
- `TravelAgentStateMachine` 的装配路径（若仍在 app 层）

### 禁止触碰（同轮）
- `main.py`（除一行 state machine import 若必须）、`tools/` 内部、`evals/`、`static/`

### 验收
```bash
cd backend
python -c "from app.orchestrator.state_machine import TravelAgentStateMachine; TravelAgentStateMachine()"
pytest app/evals/ -q -k "state_machine or evidence_planning or semantic_routing" -x --maxfail=1
```

---

## P5 — `apps/agent-python`

### 目标
`main.py`、应用启动、CORS、路由迁入 `apps/agent-python/`；`backend/` 保留兼容入口或薄 shim。

### 允许读取（≤12）
- `main.py`、`config` 引用链、uvicorn 启动方式（`RUNBOOK` 仅当用户允许）

### 允许修改
- `apps/agent-python/**`
- 根 / `backend` 启动脚本与 import shim

### 禁止触碰（同轮）
- `packages/tools` 内部、`tests/evals` 大规模改写、`static/`

### 验收
```bash
cd apps/agent-python  # 或 backend，视 shim 而定
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/api/travel/query -H "Content-Type: application/json" -d "{\"query\":\"test\"}" | head -c 200
```

---

## P6 — `apps/web`

### 目标
`static/` → `apps/web/public/`（或等价）；`main.py` 改静态路径或文档说明前后端分离。

### 允许读取（≤12）
- `main.py`（static 相关）
- `backend/app/static/` 文件列表（一层）

### 允许修改
- `apps/web/**`
- `main.py` 中 `STATIC_DIR` 与 mount 逻辑

### 禁止触碰（同轮）
- `agent_core`、`tools`、`evals/`

### 验收
```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/
# 期望 200（有 index）或 307 到 /docs
```

---

## P7 — `tests/`

### 目标
`backend/app/evals/` → `tests/evals/`；更新 `pytest.ini` 与 import。

### 允许读取（≤12/轮）
- 用户指定的 eval 文件
- `pytest.ini`

### 允许修改
- `tests/**`
- `pytest.ini`
- 测试内 `app.` import

### 禁止触碰（同轮）
- `packages/agent_core` 业务逻辑、`tools` 实现、`main.py` 路由

### 验收
```bash
cd backend  # 或 monorepo 根，视 pytest 根目录而定
pytest tests/evals/ -q --ignore=tests/evals/integration -x
```

---

## P8 — `contracts/`

### 目标
`TravelQueryRequest` / `TravelQueryResponse` 及 OpenAPI 稳定层独立；`agent-python` 与 future `api-java` 共用。

### 允许读取（≤12）
- `schemas/response.py`
- `main.py` 路由模型绑定
- 用户指定的 OpenAPI 相关文件

### 允许修改
- `contracts/**`
- `main.py` 的 schema import
- `packages/shared/schemas` 中与 API 重复部分的拆分

### 验收
```bash
curl -s http://127.0.0.1:8000/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); assert '/api/travel/query' in d.get('paths',{})"
```

---

## P9 — 收尾

### 目标
移除空的 `backend/app` 旧路径；更新文档中的启动命令；可选 `api-java` 占位 README。

### 允许修改
- 文档（**仅用户明确要求时**）
- 删除已迁移的空目录
- CI 路径（若存在）

### 验收
```bash
# 全量回归（用户确认环境后）
cd backend && pytest tests/ -q
# 手动：health + 一条 travel query
```

---

## 跨阶段规则（重申）

1. **每轮开始前**列出：计划读取 / 计划修改 / 不触碰目录。
2. **需要更多上下文**：停止并向用户索要 **具体文件路径**，禁止自行全库搜索。
3. **import 破坏风险**：每阶段只改本包相关前缀；保留 `app.*` shim 直至 P9。
4. **不要同轮交叉**：agent、api、web、tools、tests 五类至多动一类（P5 的 main 除外且不与 P4/P3 同轮）。

---

## 建议的下一轮

**P1 — 骨架目录**：仅 `mkdir` + `.gitkeep`，零 Python 变动，风险最低。

请明确指令：`执行 P1` 或指定其他阶段编号。
