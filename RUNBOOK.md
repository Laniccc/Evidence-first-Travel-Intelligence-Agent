# Evidence-first Travel Intelligence Agent — Runbook

本文档说明如何在本项目中安装、配置并运行 **东亚旅游景点情报 Agent**（Monorepo：agent-python + api-java + web），以及如何运行评测与上传 GitHub。

---

## 1. 概述

| 项目 | 说明 |
|------|------|
| Python Agent 入口 | `apps/agent-python/app/main.py`（FastAPI `:8001`） |
| API Gateway | `apps/api-java`（`:8082`，代理到 agent-python） |
| 前端 | `apps/web`（Vite dev `:5173`） |
| 状态机 | `apps/agent-python/app/orchestrator/state_machine.py` |
| 工具 / mock 数据 | `packages/tools/` |
| 首期支持区域 | 日本、中国、韩国 |

设计原则：**工具返回 Evidence → Agent 基于 Evidence 总结 → Composer 生成回答**。

---

## 2. 环境要求

- **Python** 3.11+（agent-python）
- **Java 17+ / Maven**（api-java，可选）
- **Node.js 18+**（web，可选）
- **Git**（上传 GitHub 时需要）

---

## 3. 安装（Agent 核心）

```powershell
cd apps/agent-python
pip install -r requirements.txt
copy .env.example .env
```

---

## 4. 配置

编辑 `apps/agent-python/.env`：

```env
LLM_MODE=mock
LOG_LEVEL=INFO
DEEPSEEK_API_KEY=
MCP_ENABLED=true
```

| 变量 | 说明 |
|------|------|
| `LLM_MODE` | `mock` / `auto` / `anthropic` |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（空字符串视为未配置） |
| `MCP_ENABLED` | 默认 `true` |
| `TOOL_MODE` | `mock` / `real` / `hybrid`（默认 hybrid） |

**安全提示**：不要将 `apps/agent-python/.env` 提交到 Git。

### 验证配置

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -c "from app.config import get_settings; s=get_settings(); print('llm_mode:', s.llm_mode)"
```

---

## 5. 启动服务

### 5.1 仅 Agent（最快验证）

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

```powershell
curl http://127.0.0.1:8001/agent/health
```

问答：

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/agent/query `
  -H "Content-Type: application/json; charset=utf-8" `
  -d '{"query":"京都清水寺适合带父母去吗？","session_id":"demo"}'
```

调试日志（每次问答覆盖）：`apps/agent-python/debug_last_session.md`

### 5.2 完整三件套

需要 **3 个终端**，按顺序启动。默认端口：agent-python `:8001` → api-java `:8082` → web `:5173`。

**终端 1 — agent-python**

```powershell
conda activate ClaudeAgent
cd apps/agent-python
pip install -r requirements.txt          # 首次
copy .env.example .env                   # 首次
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

验证：`curl http://127.0.0.1:8001/agent/health`

**终端 2 — api-java（需 Java 17+、Maven）**

```powershell
cd apps/api-java
# 可选：copy .env.example .env 后按需设置 AGENT_BASE_URL=http://localhost:8001
mvn spring-boot:run
```

验证：`curl http://127.0.0.1:8082/health`

**终端 3 — web 前端**

```powershell
cd apps/web
copy .env.example .env                   # 首次；VITE_API_BASE_URL 留空即可走 Vite 代理
npm install                              # 首次
npm run dev
```

浏览器打开 http://127.0.0.1:5173 ，在页面提问。开发模式下请求路径为 `POST /api/travel/query`（Vite 代理到 `http://localhost:8082`）。

**链路确认**

```text
浏览器 :5173  →  Vite proxy  →  api-java :8082  →  agent-python :8001
```

无 Maven 时见 [apps/web/README.md](apps/web/README.md)「临时绕过 api-java」（Vite 直连 `:8001`，测完改回）。

---

## 6. API 字段

| 字段 | 说明 |
|------|------|
| `answer` | 自然语言回答 |
| `visible_trace` | 执行轨迹（思考日志） |
| `evidence_summary` | 证据摘要 |
| `limitations` | 限制说明 |
| `tool_traces` | 工具调用轨迹 |

---

## 7. 运行评测

```powershell
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
pytest app/evals -q
```

Golden queries：`apps/agent-python/app/evals/golden_queries.json`

---

## 8. 目录结构

```text
apps/agent-python/     # Python Agent（主开发目录）
apps/api-java/         # Java Gateway
apps/web/              # 前端
packages/tools/        # 工具与 mock 数据
contracts/             # JSON Schema
```

详见 [REPO_MAP.md](REPO_MAP.md)。

---

## 9. 故障排查

| 现象 | 处理 |
|------|------|
| `ModuleNotFoundError: app` | `cd apps/agent-python`，设置 `PYTHONPATH=.` |
| 区域显示「未知」 | 检查 `DEEPSEEK_API_KEY`；城市是否在 `packages/tools/mock/data.py` 的 `CITY_COUNTRY` |
| 回答空 / 0 evidence | 查看 `debug_last_session.md` 的 trace |
| 端口占用 | 换 `--port` |
| `LLM_MODE=mock` 回答模板化 | 配置 API key 后设 `LLM_MODE=anthropic` |

---

## 10. 上传 GitHub

```powershell
.\upload_to_github.ps1 -Message "your message"
```

`.gitignore` 已排除 `apps/agent-python/.env`、`.npm-cache/`、`node_modules/` 等。

---

## 11. 快速检查清单

- [ ] `cd apps/agent-python && pip install -r requirements.txt`
- [ ] `apps/agent-python/.env` 已创建
- [ ] `http://127.0.0.1:8001/agent/health` 正常
- [ ] `POST /agent/query` 返回 `answer` + `visible_trace`
- [ ] `pytest app/evals -q` 通过
- [ ] 上传前确认 `.env` 未被 `git add`

---

*文档版本：Monorepo（`apps/agent-python` 为唯一 Python 运行时）。*
