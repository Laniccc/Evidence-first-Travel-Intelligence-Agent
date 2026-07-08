# MIGRATION_PLAN — Monorepo 分阶段迁移计划

> **状态（2026-06）**：`backend/` 已从仓库删除；**唯一 Python 运行时**为 `apps/agent-python/`。  
> **原则**：新功能只写 `apps/*`、`packages/`、`contracts/`。

## 目标结构

```
Evidence-first Travel Intelligence Agent/
├── apps/
│   ├── agent-python/      # Python Agent 核心（主运行时）
│   ├── api-java/            # Java API Gateway / session / 周边服务
│   └── web/                 # 前端
├── packages/                # 可选：tools、shared 等复用包
├── contracts/               # 跨语言协议（JSON Schema）
├── tests/                   # evals、集成测试
├── backend/                 # LEGACY — 回退与对照 only
├── docs/
├── REPO_MAP.md
└── MIGRATION_PLAN.md
```

---

## Round 0 — 冻结 Legacy（已完成）

### 目标
- 新增 `backend/LEGACY.md`
- 文档标明 `backend/` = legacy；新开发以 `apps/*` + `contracts/` 为准

### 验收
```bash
test -f backend/LEGACY.md
grep -qi legacy REPO_MAP.md README.md MIGRATION_PLAN.md
```

---

## 已完成（壳层 / 准备）

| 轮次 | 内容 |
|------|------|
| Web 迁移 | `apps/web/dist`；legacy `main.py` 可选挂载 |
| R2–R3 | `apps/agent-python`、`packages/tools` 副本 |
| R4–R6 | `apps/api-java` + HTTP 代理；`contracts/json-schema` |

**过渡期**：仍可 `cd backend && uvicorn app.main:app` 作回退；**新功能写入目标目录**。

---

## 后续阶段（按应用分轨修复）

> 顺序：**agent-python → api-java → web → contracts** 各轨独立推进；每轨内再分子阶段。  
> 同轮不交叉修改 agent / api / web / contracts / tests。

### 轨道 A — `apps/agent-python`（Python Agent 核心）

| 阶段 | 目标 | 验收 |
|------|------|------|
| **A1** | 迁入 `main.py`、`config`、启动脚本；`backend` 仅留 redirect 说明 | `uvicorn` 从 `apps/agent-python` 启动 |
| **A2** | 迁入 `orchestrator/`、`policies/`、`prompts/`、`catalog/`、`llm_client.py` | `TravelAgentStateMachine` 可实例化 |
| **A3** | 迁入 / 对接 `packages/tools`、`packages/shared` | `POST /api/travel/query` 200 |
| **A4** | 评测迁出 `backend/app/evals` → `tests/evals` | `pytest tests/evals -q` |

**允许读取/修改（每轮 ≤12 读 / ≤20 改）**：`apps/agent-python/**`、`packages/**`（若 A3）、用户指定 legacy 对照文件只读。

**禁止**：同轮改 `apps/api-java`、`apps/web`、`contracts`（除只读对照）。

```bash
cd apps/agent-python   # 或文档约定路径
python -m compileall .
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/api/travel/query \
  -H "Content-Type: application/json" -d '{"query":"test"}' | head -c 200
```

---

### 轨道 B — `apps/api-java`（Gateway / session / 周边）

| 阶段 | 目标 | 验收 |
|------|------|------|
| **B1** | 代理指向 `apps/agent-python` 新端口/路径 | Java → Python query 200 |
| **B2** | Session / 用户上下文（若需要） | 集成测试通过 |
| **B3** | 周边服务占位（鉴权、限流等） | `mvn test` |

**允许修改**：`apps/api-java/**`、`contracts/`（若绑定 DTO）

**禁止**：同轮改 `apps/agent-python` 业务逻辑

```bash
cd apps/api-java
mvn -q test
curl -s http://127.0.0.1:8080/health/agent
```

---

### 轨道 C — `apps/web`（前端）

| 阶段 | 目标 | 验收 |
|------|------|------|
| **C1** | API base URL 指向 Java Gateway 或 Python Agent | UI 可提交 query |
| **C2** | 构建流水线（`dist/`） | 静态资源可独立部署 |
| **C3** | Legacy API 去掉 static 挂载（可选） | `/` 不再依赖 backend |

**允许修改**：`apps/web/**` only

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/static/index.html
```

---

### 轨道 D — `contracts`（跨语言协议）

| 阶段 | 目标 | 验收 |
|------|------|------|
| **D1** | Schema 与 `apps/agent-python` 响应对齐 | 样例 JSON 通过 schema 校验 |
| **D2** | Java DTO / 校验与 schema 绑定 | `mvn test` |
| **D3** | OpenAPI 生成或导出（可选） | `openapi.json` 与 contracts 一致 |

**允许修改**：`contracts/**`、绑定层薄代码（用户指定文件）

```bash
# 用户环境安装 jsonschema 后
python -c "import json,jsonschema; ..."   # 按 D1 脚本为准
```

---

## Legacy `backend/` 收尾（轨道 E，最后执行）

| 阶段 | 目标 |
|------|------|
| **E1** | `backend/README` 指针 → `LEGACY.md` |
| **E2** | 删除或最小化 `backend/app` 业务代码，仅保留 shim |
| **E3** | 文档与 RUNBOOK 全面切换至 monorepo 路径 |

**前置条件**：轨道 A–D 验收通过。

---

## 跨阶段规则

1. 每轮列出：**计划读取 / 计划修改 / 不触碰目录**。
2. 需要更多上下文：**向用户索要具体文件路径**（≤12 源码文件/轮）。
3. **`backend/` 冻结**：新功能不写 legacy；对照只读。
4. 保留 `app.*` shim 直至轨道 E。
5. **不要同轮交叉**五类：agent-python、api-java、web、contracts、tests。

---

## 建议下一轮

**轨道 A1** — 将 FastAPI 入口迁入 `apps/agent-python`（用户指令：`执行 A1`，并列出允许读取的文件）。
