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
