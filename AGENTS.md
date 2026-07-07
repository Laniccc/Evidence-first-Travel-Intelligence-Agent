# Deep Research Agent Platform

AI-powered autonomous research agent — Java Spring Boot + Python AI Engine.

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

See [README.md](README.md) and [RUNBOOK.md](RUNBOOK.md) for details.

## Development Conventions

- All facts must be backed by `Evidence` objects with source URLs
- Agent pipeline: 6 phases → 7 quality gates → cited report
- Source quality: 5-tier rating (Tier-1 academic → Tier-5 spam)
- Agent Core state: `apps/agent-python/app/agent_core/`
- Config: `apps/agent-python/app/config.py`
