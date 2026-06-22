# Evidence-first Travel Intelligence Agent — Runbook

本文档说明如何在本机**安装、配置、启动、测试与排错**。项目设计与功能说明见 [README.md](README.md)。

---

## 1. 服务一览

| 服务 | 目录 | 端口 | 健康 / 入口 |
|------|------|------|-------------|
| agent-python | `apps/agent-python` | **8001** | `GET /agent/health` |
| api-java | `apps/api-java` | **8080** | 见 Java 启动日志 |
| web | `apps/web` | **5173** | http://127.0.0.1:5173 |

正常链路：`web → api-java /api/travel/query → agent-python /agent/query`

---

## 2. 环境要求

| 依赖 | 版本 / 说明 |
|------|-------------|
| Python | 3.11+（推荐 **Conda** 环境） |
| Node.js | 18+（仅前端） |
| Java | 17+（api-java） |
| Maven | 3.9+（`mvn -version` 验证） |
| Git | 上传 GitHub 时需要 |

可选：`DEEPSEEK_API_KEY` 等；无 key 时 `LLM_MODE=mock` 可离线演示。

---

## 3. 安装

### 3.1 agent-python（必须）

```powershell
conda activate ClaudeAgent          # 替换为你的 conda 环境名
cd apps/agent-python
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

### 3.2 api-java（完整链路）

```powershell
cd apps/api-java
mvn -q -DskipTests package
```

### 3.3 web（前端）

```powershell
cd apps/web
copy .env.example .env
npm install
```

---

## 4. 配置

### 4.1 agent-python — `apps/agent-python/.env`

```env
LLM_MODE=mock
LOG_LEVEL=INFO

# 真实 LLM（可选）
# LLM_MODE=anthropic
# DEEPSEEK_API_KEY=sk-...
# DEEPSEEK_MODEL=deepseek-v4-flash
# ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic

# 工具模式
TOOL_MODE=hybrid
ENABLE_REAL_WEATHER=false
ENABLE_REAL_PLACES=false
ENABLE_REAL_OFFICIAL_PAGE=false
MCP_ENABLED=false
REAL_TOOL_TIMEOUT_SECONDS=8
REAL_TOOL_CACHE_TTL_SECONDS=3600

# Java Tool Gateway（可选，需 api-java）
USE_JAVA_TOOL_GATEWAY=false
TOOL_GATEWAY_BASE_URL=http://localhost:8080
```

| 变量 | 说明 |
|------|------|
| `LLM_MODE` | `mock` / `auto` / `anthropic` |
| `TOOL_MODE` | `mock` / `real` / `hybrid`（默认） |
| `ENABLE_REAL_WEATHER` | `true` + `WEATHER_API_KEY`（[OpenWeatherMap](https://openweathermap.org/api)） |
| `ENABLE_REAL_PLACES` | `true` + `PLACES_API_KEY=pilot`（Nominatim 试点） |
| `ENABLE_REAL_OFFICIAL_PAGE` | `true`（白名单见 `app/config.py`） |

**安全**：勿将 `.env` 提交 Git。

### 4.2 web — `apps/web/.env`

```env
# 开发默认由 Vite 代理到 api-java
VITE_API_BASE_URL=http://localhost:8080
```

### 4.3 验证配置

```powershell
conda activate ClaudeAgent
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -c "from app.config import get_settings; s=get_settings(); print('llm_mode:', s.llm_mode, 'tool_mode:', s.tool_mode)"
```

---

## 5. 启动服务

需要 **3 个终端**（完整链路）：

### 终端 1 — agent-python

```powershell
conda activate ClaudeAgent
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

验证：http://127.0.0.1:8001/agent/health  
（`:8001/` 根路径 404 为正常现象。）

### 终端 2 — api-java

```powershell
cd apps/api-java
mvn spring-boot:run
```

### 终端 3 — web

```powershell
cd apps/web
npm run dev
```

浏览器打开：http://127.0.0.1:5173

---

## 6. 临时绕过 api-java（无 Maven / 快速验 UI）

无法或未启动 `api-java` 时，可让 Vite 直接把 `/api/travel/query` 转到 agent-python。

**限制**：无 Java 会话记忆、无 Java Tool Gateway。

1. 保持终端 1 的 agent-python 运行（8001）
2. 编辑 `apps/web/vite.config.js`，将 `server.proxy` 中 `/api` 块替换为：

```javascript
proxy: {
  "/api": {
    target: "http://localhost:8001",
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api\/travel\/query/, "/agent/query"),
  },
},
```

3. `cd apps/web && npm run dev` → http://127.0.0.1:5173

**恢复正式链路**：改回 `target: apiBase`（删除 `rewrite`），并启动 api-java。

详见 [apps/web/README.md](apps/web/README.md)。

---

## 7. API 使用示例

### 7.1 经 Java Gateway（完整链路）

```powershell
$json = '{"query":"京都清水寺适合带父母去吗？","user_context":{"party":["elderly"],"pace":"relaxed"}}'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/travel/query `
  -ContentType "application/json; charset=utf-8" `
  -Body $bytes
```

### 7.2 直连 agent-python

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$json = '{"query":"京都清水寺适合带父母去吗？","session_id":"demo-session"}'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/agent/query `
  -ContentType "application/json; charset=utf-8" `
  -Body $bytes
```

**PowerShell + curl**（`-d` 必须用单引号）：

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/agent/query `
  -H "Content-Type: application/json; charset=utf-8" `
  -d '{"query":"京都清水寺适合带父母去吗？","session_id":"demo-session"}'
```

若仍报 `JSON decode error`，将 JSON 写入 UTF-8 无 BOM 文件后用 `--data-binary "@文件路径"`。详见 [apps/agent-python/README.md](apps/agent-python/README.md)。

### 7.3 更多示例 query

| 场景 | query 示例 |
|------|-----------|
| 多景点比较 | `清水寺、伏见稻荷、岚山竹林哪个更适合老人？` |
| 轻量行程 | `我住在明洞，想安排一天首尔文化游。` |

响应字段说明见 [README.md — API 响应字段](README.md#api-响应字段契约摘要)。

---

## 8. 运行评测

### agent-python 单元测试

```powershell
conda activate ClaudeAgent
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/ -q
```

### Legacy evals（对照，可选）

```powershell
cd backend
pytest app/evals -q
pytest app/evals/integration -m real_api -q    # 无 API key 自动 skip
```

Golden queries：`backend/app/evals/golden_queries.json`  
Real Data Pilot：`backend/app/evals/real_data_pilot_queries.json`

---

## 9. 生产构建（前端）

```powershell
cd apps/web
$env:VITE_API_BASE_URL="https://api.example.com"
npm run build
```

产物：`apps/web/dist/`。部署时由反向代理将 `/api` 转到 api-java。

---

## 10. Legacy 单体回退

仅对照或紧急回退时使用；**新功能勿写入 `backend/`**。

```powershell
conda activate ClaudeAgent
cd backend
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

| 地址 | 说明 |
|------|------|
| http://127.0.0.1:8000/ | 重定向（legacy） |
| http://127.0.0.1:8000/admin | Swagger |
| http://127.0.0.1:8000/health | 健康检查 |

详见 [backend/LEGACY.md](backend/LEGACY.md)。

---

## 11. 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `ModuleNotFoundError: No module named 'app'` | 工作目录或 PYTHONPATH 错误 | `cd apps/agent-python`，设 `$env:PYTHONPATH = (Get-Location).Path` |
| `:8001/` 返回 404 | 无根路由 | 使用 `/agent/health` 或前端 `:5173` |
| 端口 8001 / 8080 占用 | 旧进程未退出 | 结束对应进程或换 `--port` |
| PowerShell 中文乱码 | 控制台非 UTF-8 | `chcp 65001` + UTF-8 字节发 Body（见 §7.2） |
| curl `JSON decode error` | PowerShell 改写 `-d` | `-d` 用单引号，或写文件 `--data-binary` |
| 前端无法连 API | api-java 未启动 | 启动 `:8080` 或 §6 临时绕过 Java |
| `query_scope=unknown` | mock LLM 或编码问题 | 检查 UTF-8 与 `LLM_MODE` |
| 回答过于模板化 | `LLM_MODE=mock` | 配置 API Key，设 `LLM_MODE=anthropic` |
| 真实天气未生效 | key 或未启用 | `ENABLE_REAL_WEATHER=true`；查 `tool_traces.fallback_used` |
| 景点未识别 | mock 库无条目 | `packages/tools` mock 数据 / `PLACE_REGISTRY` |
| 非日韩中查询被拒 | Region Gate 设计 | 预期行为 |
| Maven 找不到 | PATH 未配置 | `mvn -version`；或 §6 绕过 Java |

---

## 12. 上传项目到 GitHub

默认远程：**https://github.com/Laniccc/Evidence-first-Travel-Intelligence-Agent.git**（分支 `main`）

### 12.1 不会上传的内容

| 路径/模式 | 说明 |
|-----------|------|
| `**/.env` | API 密钥 |
| `__pycache__/`、`.pytest_cache/` | 缓存 |
| `*.pat`、`github-pat.txt` | 令牌 |
| `node_modules/` | 前端依赖 |

### 12.2 一键上传（Windows）

```powershell
.\upload_to_github.ps1
.\upload_to_github.ps1 -Message "feat: update runbook"
.\upload_to_github.ps1 -DryRun
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `-RemoteUrl` | 见上 | 远程地址 |
| `-Branch` | `main` | 分支 |
| `-Message` | `init: ...` | 提交说明 |
| `-DryRun` | — | 仅预览 |

**macOS / Linux**：`bash upload_to_github.sh`

### 12.3 GitHub 凭据（HTTPS + PAT）

1. [GitHub Tokens](https://github.com/settings/tokens) → classic → 勾选 `repo`
2. 本仓库独立凭据：`.\setup_project_credentials.ps1`
3. 推送失败：`.\fix_github_auth.ps1`

---

## 13. 运维与安全

1. 密钥仅放 `apps/agent-python/.env`（及 Java 侧配置），勿提交 Git
2. 接真实 API 时遵守平台 ToS；mock 阶段只存摘要
3. 不绕过登录、验证码或批量抓取受保护内容
4. 缺少关键证据时必须在 `limitations` 标注，不得给虚假确定性结论

---

## 14. 快速检查清单

- [ ] Conda 环境已激活，`pip install -r apps/agent-python/requirements.txt` 成功
- [ ] `apps/agent-python/.env` 已创建（`LLM_MODE=mock` 即可）
- [ ] agent-python 可访问 http://127.0.0.1:8001/agent/health
- [ ] （完整链路）api-java `:8080`、web `:5173` 已启动
- [ ] `POST /agent/query` 或经 Gateway 的 `POST /api/travel/query` 返回 `answer` + `visible_trace`
- [ ] `pytest` 通过
- [ ] 上传前确认 `.env` 未被 `git add`

---

*Runbook 与当前 `apps/` monorepo 运行时一致；变量与端口以各 app 代码为准。*
