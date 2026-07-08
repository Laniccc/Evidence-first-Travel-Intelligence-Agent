# Evidence-first Travel Intelligence Agent

Java Spring Boot + Python FastAPI + Web frontend.

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

See [README.md](README.md) and [RUNBOOK.md](RUNBOOK.md).

## Development Conventions

- Facts must be backed by `Evidence` objects with source URLs.
- Python runtime entrypoint: `apps/agent-python/app/main.py`.
- Agent state machine: `apps/agent-python/app/orchestrator/state_machine.py`.
- Java gateway runtime: `apps/api-java/src/main/java/`.
- Frontend runtime: `apps/web/src/`.
- Keep generated caches, debug output, build output, and external vendor clones out of Git.
