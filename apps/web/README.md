# apps/web — 前端

静态 SPA，通过 **Java API Gateway** 调用旅行问答 API。

```
浏览器 → VITE_API_BASE_URL (默认 http://localhost:8080)
           POST /api/travel/query
                → api-java → agent-python /agent/query
```

**前端绝不请求** `/agent/query` 或 Python `:8001`。

## 前置条件

1. **agent-python**（:8001）
2. **api-java**（:8080）

## 开发启动

```powershell
cd apps/web
copy .env.example .env
npm install
npm run dev
```

打开 http://127.0.0.1:5173

开发模式下 Vite 将 `/api/*` 代理到 `VITE_API_BASE_URL`（默认 8080），因此浏览器网络面板中应只看到：

- `POST http://127.0.0.1:5173/api/travel/query`（由 dev server 转发到 api-java）

不会出现 `/agent/query` 或 `:8001`。

## 临时绕过 api-java（无 Maven）

本地未安装 Maven、无法启动 `api-java` 时，可 **临时** 让 Vite 把前端请求直接转到 `agent-python`，用于验证页面与 Agent 问答。

**限制**：无 Java 会话记忆、无 Java Tool Gateway；测完请改回默认配置。

### 1. 启动 agent-python（终端 1）

```powershell
conda activate ClaudeAgent
cd apps/agent-python
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

确认：`http://127.0.0.1:8001/agent/health` 返回正常。

### 2. 修改 Vite 代理（一次性，测完还原）

编辑 `apps/web/vite.config.js`，将 `server.proxy` 中的 `/api` 块 **整段替换** 为：

```javascript
proxy: {
  "/api": {
    target: "http://localhost:8001",
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api\/travel\/query/, "/agent/query"),
  },
},
```

默认（走 Java）为：

```javascript
proxy: {
  "/api": {
    target: apiBase,
    changeOrigin: true,
  },
},
```

### 3. 启动前端（终端 2）

```powershell
cd apps/web
npm install
npm run dev
```

打开 http://127.0.0.1:5173 ，在页面输入旅行问题即可。

浏览器仍请求 `POST /api/travel/query`，由 Vite 改写为 `POST http://localhost:8001/agent/query`。

### 4. 恢复正式链路

把 `vite.config.js` 改回 `target: apiBase`（删除 `rewrite`），并启动 `api-java`（:8080）后再 `npm run dev`。

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
