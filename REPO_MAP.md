# REPO_MAP — 当前仓库职责映射

## 根目录

| 路径 | 职责 |
|------|------|
| `apps/agent-python/` | **Python Agent 核心**（orchestrator、agents、FastAPI `:8001`） |
| `apps/api-java/` | **Java API Gateway** / session（`:8080` → Python） |
| `apps/web/` | **前端** SPA |
| `contracts/` | **跨语言协议**（JSON Schema） |
| `packages/tools/` | 工具注册、MCP、Mock/Real/Hybrid、mock 数据真相源 |
| `docs/` | 项目文档 |

## 依赖关系

```
浏览器 → apps/web (:5173)
           → apps/api-java (:8080)
                → apps/agent-python (:8001)
                     → packages/tools

contracts/ ◄── apps/api-java, apps/agent-python
```

## 开发约定

1. **新功能只写** `apps/agent-python/`、`packages/`、`contracts/`、`apps/web/`、`apps/api-java/`。
2. **评测**在 `apps/agent-python/app/evals/` 运行：`pytest app/evals -q`。
3. **调试日志**：`apps/agent-python/debug_last_session.md`（每次 `/agent/query` 覆盖写入）。
