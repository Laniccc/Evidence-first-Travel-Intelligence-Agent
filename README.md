# Evidence-first Travel Intelligence Agent

Evidence-first Travel Intelligence Agent 是一个本地可运行的旅行问答 Agent：Python FastAPI 负责 Agent 编排，Java Spring Boot 可作为 API Gateway，Web 提供前端界面。

核心原则：所有事实性回答都应来自 `Evidence` 对象和来源 URL，回答层只基于证据、工具 trace 和限制说明进行组织。

## Quickstart

```powershell
# Terminal 1: Python Agent
cd apps/agent-python
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Terminal 2: Java Backend
cd apps/api-java
mvn spring-boot:run

# Terminal 3: Frontend
cd apps/web
npm run dev
```

也可以从仓库根目录使用辅助脚本启动 Python Agent、MCP 搜索和 Web：

```powershell
.\scripts\start-agent.ps1
```

## Services

| Service | URL |
| --- | --- |
| Web | http://127.0.0.1:5173/ |
| Python Agent health | http://127.0.0.1:8001/agent/health |
| Python Agent query | POST http://127.0.0.1:8001/agent/query |
| Java Gateway | http://127.0.0.1:8082/ |

## Runtime Structure

```text
apps/agent-python/     Python Agent and basic tests
apps/api-java/         Java API Gateway and tests
apps/web/              Frontend SPA
packages/tools/        Shared tool implementations
contracts/schemas/     JSON schema contracts
scripts/               Runtime helper scripts
```

保留的测试只覆盖基础运行面：

```powershell
cd apps/agent-python
python -m compileall app -q
python -m pytest tests -q

cd ..\api-java
mvn test

cd ..\web
npm run build
```

## Configuration

复制并编辑环境变量：

```powershell
copy apps\agent-python\.env.example apps\agent-python\.env
copy apps\web\.env.example apps\web\.env
copy apps\api-java\.env.example apps\api-java\.env
```

默认配置保持外部爬虫和付费/真实 API 关闭。需要接入真实工具时，在 `.env` 中启用对应 provider，并为 crawler 类工具显式填写命令和工作目录。

更多运行细节见 [RUNBOOK.md](RUNBOOK.md)。
