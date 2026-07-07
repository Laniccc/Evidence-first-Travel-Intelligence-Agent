# Deep Research Agent Platform

Evidence-first autonomous research agent with Java Spring Boot business backend + Python AI engine.

## Quickstart

```powershell
cd apps/agent-python
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

See [RUNBOOK.md](RUNBOOK.md) and [README.md](README.md).

## Dev Conventions

- All facts must derive from `Evidence` objects with source URLs
- 6-phase pipeline: planning → knowledge_retrieval → evidence_acquisition → evidence_extraction → synthesis → knowledge_upsert
- 7 quality gates (non-blocking): input → plan → source → evidence → crossref → citation → delivery
- Source quality: Tier 1-5 rating with automatic Tier-5 discard
- State chain: `apps/agent-python/app/agent_core/`
- Agent Core store: SQLite (prod) or Memory (dev)
- Debug log: `apps/agent-python/debug_last_session.md`
