# Evidence-first Travel Intelligence Agent

Java Spring Boot platform + Python FastAPI Travel Agent + Web frontend.

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
- Agent state machine: `apps/agent-python/app/orchestration/state_machine.py`.
- Java platform runtime: `apps/api-java/src/main/java/`.
- Java package standard: `domain`, `application`, `infrastructure`, `web`, plus `dto` under web or integration boundaries.
- Java platform domains: `user`, `platform`, `agent`, `tool`, with cross-cutting `common` and `infrastructure.security`.
- New Java features must be placed by domain first, then by layer. Controllers stay in `web`; use cases stay in `application`; business state stays in `domain`; persistence and external clients stay in `infrastructure`.
- Python Agent implementation layers are `api`, `contracts`, `context`, `understanding`, `planning`, `execution`, `tools`, `integrations`, `evidence`, `composition`, `orchestration`, `governance`, and `observability`. New Python code must go directly into its capability owner.
- `app.agents`, `app.orchestrator`, `app.schemas`, `app.tool_gateway`, `app.storage`, `app.catalog`, `app.prompts`, and `app.policies` are retired. Do not import or recreate them. `app.contract` is the sole allowed compatibility module and may only re-export public contracts from `app.contracts`.
- Java owns business platform data: users, auth, conversations, query history, favorites, profiles, and future billing/subscriptions. Python owns a single Agent run and returns intelligence output.
- Java-Python contract changes require tests on both sides: Java client/platform tests and Python contract/API tests.
- API contracts used by the frontend must be tested or covered by a platform flow test before changing UI behavior.
- Frontend platform runtime: `apps/web/src/`.
- Keep generated caches, debug output, build output, and external vendor clones out of Git.
