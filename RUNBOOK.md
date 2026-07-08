# Runbook

## Ports

| Component | Port | Notes |
| --- | ---: | --- |
| Web | 5173 | Vite dev server |
| Python Agent | 8001 | FastAPI |
| Java Gateway | 8082 | Spring Boot |
| MCP search | 3210 | Optional open-webSearch helper |

## Install

```powershell
cd apps/agent-python
pip install -r requirements.txt
copy .env.example .env

cd ..\web
npm install

cd ..\api-java
mvn test
```

## Start

Python Agent:

```powershell
cd apps/agent-python
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Java Gateway:

```powershell
cd apps/api-java
mvn spring-boot:run
```

Web:

```powershell
cd apps/web
npm run dev
```

Root helper:

```powershell
.\scripts\start-agent.ps1
```

Useful helper flags:

```powershell
.\scripts\start-agent.ps1 -NoMcp
.\scripts\start-agent.ps1 -NoWeb
.\scripts\start-agent.ps1 -WebOnly
.\scripts\start-agent.ps1 -WebViaGateway
.\scripts\start-agent.ps1 -Port 8002
```

## Verify

```powershell
cd apps/agent-python
python -m compileall app -q
python -m pytest tests -q

cd ..\api-java
mvn test

cd ..\web
npm run build
```

Health check:

```powershell
curl http://127.0.0.1:8001/agent/health
```

Query example:

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/agent/query `
  -H "Content-Type: application/json; charset=utf-8" `
  -d '{"query":"京都清水寺适合带父母去吗？","session_id":"demo"}'
```

## Notes

- `apps/agent-python/debug_last_session.md` is generated locally and ignored by Git.
- External crawlers are not vendored. Configure crawler commands explicitly in `apps/agent-python/.env` if needed.
- SQLite/cache/debug files are local runtime artifacts and should remain untracked.
- The Java backend is optional for local direct-agent development, but kept as the gateway integration path.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'app'` | Run from `apps/agent-python`, or use `.\scripts\start-agent.ps1` from repo root. |
| Browser shows `405` for `/agent/query` | Use `POST`; `GET` is expected to fail. |
| Web request times out | Confirm Python Agent is on `:8001`; if using gateway mode, confirm Java is on `:8082`. |
| MCP search unavailable | Start without MCP using `.\scripts\start-agent.ps1 -NoMcp`, or inspect `logs/mcp/*.log`. |
| Real tools return mock/fallback evidence | Check `.env` flags and API keys, then restart the process. |
