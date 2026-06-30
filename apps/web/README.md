# apps/web — 前端

静态 SPA。本地开发默认通过 Vite 将 `/api/travel/query` 直连到 **agent-python**；需要完整 Java Gateway 链路时，可显式配置 `VITE_API_BASE_URL` 或用启动脚本参数 `-WebViaGateway`。

```
本地默认：
浏览器 → Vite :5173 → agent-python /agent/query (:8001)

完整链路 / 生产：
浏览器 → Vite :5173 或 VITE_API_BASE_URL（如 http://localhost:8082）
           POST /api/travel/query
                → api-java → agent-python /agent/query
```

浏览器侧仍只请求 `/api/travel/query`；是否转到 `agent-python` 或 `api-java` 由 Vite 代理决定。

复杂检索类问题可能需要 **1–3 分钟**；前端 `VITE_QUERY_TIMEOUT_MS=300000` 与后端长查询超时对齐。

## 前置条件

1. **agent-python**（:8001）
2. **api-java**（:8082，可选；完整 Gateway 链路需要）

## 开发启动

```powershell
cd apps/web
copy .env.example .env
npm install
npm run dev
```

打开 http://127.0.0.1:5173

开发模式下浏览器网络面板中应只看到：

- `POST http://127.0.0.1:5173/api/travel/query`

本地默认由 Vite 改写为 `POST http://localhost:8001/agent/query`。如果设置了 `VITE_API_BASE_URL=http://localhost:8082`，则转发到 api-java。

## 本地默认直连 agent-python

本地未安装 Maven、无法启动 `api-java` 时，无需修改代码；默认配置会让 Vite 把前端请求直接转到 `agent-python`，用于验证页面与 Agent 问答。

**限制**：无 Java 会话记忆、无 Java Tool Gateway。完整链路见下方“走 Java Gateway”。

### 1. 启动 agent-python（终端 1）

```powershell
conda activate ClaudeAgent
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

确认：`http://127.0.0.1:8001/agent/health` 返回正常。

### 2. 启动前端（终端 2）

```powershell
cd apps/web
npm install
npm run dev
```

打开 http://127.0.0.1:5173 ，在页面输入旅行问题即可。

浏览器仍请求 `POST /api/travel/query`，由 Vite 改写为 `POST http://localhost:8001/agent/query`。

## 走 Java Gateway

启动 `api-java`（:8082）后，选择一种方式：

```powershell
$env:VITE_DIRECT_AGENT="false"
$env:VITE_API_BASE_URL="http://localhost:8082"
npm run dev
```

或在仓库根目录：

```powershell
.\scripts\start-agent.ps1 -WebViaGateway
```

## 生产构建

```powershell
npm run build
```

产物在 `dist/`。部署时需：

- 将 `VITE_API_BASE_URL` 设为生产环境 api-java 地址后 **再执行 build**（Vite 构建时注入）
- 或由反向代理把 `/api` 转到 api-java

```powershell
# 示例：构建时指定 API
$env:VITE_API_BASE_URL="https://api.example.com"
npm run build
```

## 目录

```
apps/web/
├── index.html
├── vite.config.js
├── src/
│   ├── main.js           # 页面逻辑
│   ├── styles.css
│   └── api/
│       ├── travel.js     # API client（仅 /api/travel/query）
│       └── types.js      # JSDoc 契约类型
├── dist/                 # npm run build 输出
└── .env.example
```

## 展示字段

页面展示 `answer`、`confidence`、`limitations`、`visible_trace`、`evidence_summary`、`tool_traces`（与 contracts 对齐）。
