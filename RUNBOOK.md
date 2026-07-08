# Runbook — Deep Research Agent Platform

Operations manual for local development, debugging, and verification.

## 1. Services & Ports

| Service | Port | Health Check | Notes |
|---------|------|-------------|-------|
| Python Agent | 8001 | `GET /agent/health` | Core research engine |
| Java Backend | 8082 | `GET /api/health` | Auth + project CRUD + agent proxy |
| MCP Search | 3210 | `GET /health` | open-websearch (Baidu/Sogou/Bing) |
| Vue Frontend | 3000 | `GET /` | Dev server (`npm run dev`) |

## 2. Startup

### One-Click (Recommended)

```powershell
# Windows — starts all 4 services in background
.\scripts\start-all.ps1

# Mac / Linux
bash scripts/start-all.sh
```

This single command starts the MCP Search stack, Python Agent, Java Backend, and Vue Frontend. Each service runs in the background; logs land in `logs/`. Press **Ctrl+C** to stop everything cleanly.

**Selective startup flags:**

| Flag | Effect |
|------|--------|
| `-NoMcp` / `--no-mcp` | Skip MCP search (use if already running) |
| `-NoAgent` / `--no-agent` | Skip Python Agent |
| `-NoJava` / `--no-java` | Skip Java Backend |
| `-NoFrontend` / `--no-frontend` | Skip Vue Frontend |
| `-AgentOnly` / `--agent-only` | Only Python Agent + MCP |
| `-SkipHealthCheck` / `--skip-health` | Don't wait for readiness probes |
| `-HealthTimeout 180` / `--timeout 180` | Custom health-check timeout (seconds) |

```powershell
# Examples
.\scripts\start-all.ps1 -AgentOnly                        # Just MCP + Python
.\scripts\start-all.ps1 -NoJava -NoFrontend               # MCP + Python only
bash scripts/start-all.sh --no-frontend                   # Skip Vue
```

### Manual (3 separate terminals)

```bash
# Terminal 1: MCP Search
npx open-websearch@latest serve --port 3210

# Terminal 2: Python Agent
cd apps/agent-python
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Terminal 3: Java Backend
cd apps/api-java
mvn spring-boot:run

# Terminal 4 (optional): Vue Frontend
cd apps/web
npm run dev
```

### Docker

```bash
docker compose up
```

### Verify All Services

```bash
curl -s http://127.0.0.1:8001/agent/health | jq .status     # "ok"
curl -s http://127.0.0.1:8082/api/health | jq .status        # "ok"
curl -s http://127.0.0.1:3210/health | jq .status            # "ok"
curl -s http://127.0.0.1:3000                                # Vue dev server
```

## 3. Query Examples

### Direct to Python Agent

```bash
curl -s -X POST http://127.0.0.1:8001/agent/query \
  -H "Content-Type: application/json" \
  -d '{"query":"What are the key trends in AI agents in 2025?"}' | jq .
```

Response shape:
```json
{
  "status": "completed",
  "run_id": "run_ecedfb6fb98e",
  "report": {
    "title": "Key Trends in AI Agents in 2025",
    "summary": "In 2025, agentic AI is recognized...",
    "sections": [...],
    "citations": [{"id":1,"title":"...","url":"...","tier":2}],
    "limitations": ["..."]
  },
  "evidence_count": 10,
  "phases_completed": ["planning","knowledge_retrieval","evidence_acquisition",
                        "evidence_extraction","synthesis","knowledge_upsert"]
}
```

### Via Java Backend (with auth)

```bash
# Register
curl -s -X POST http://127.0.0.1:8082/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"a@b.com","password":"demo123"}'

# Login → get token
TOKEN=$(curl -s -X POST http://127.0.0.1:8082/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123"}' | jq -r '.token')

# Research query
curl -s -X POST http://127.0.0.1:8082/api/research/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is an AI agent?"}' | jq .
```

## 4. Agent Core Internals

### Phase Order

```
planning → knowledge_retrieval → evidence_acquisition
→ evidence_extraction → synthesis → knowledge_upsert
```

### Gate Checks

| Gate | Phase | Failure Behavior |
|------|-------|-----------------|
| Input | Before planning | Returns clarification to user (only hard gate) |
| Plan | After planning | Auto-retry LLM decomposition (max 3) |
| Source | After evidence_acquisition | Discard Tier-5, retry with different engine |
| Evidence | After evidence_extraction | Auto-supplement search (max 2) |
| Cross-Ref | Before synthesis | Mark unverified claims in report |
| Citation | After synthesis | Remove/annotate uncited claims |
| Delivery | Before response | Degrade to partial report |

All gates except Input are **non-blocking** — they degrade gracefully rather than stopping the pipeline.

### Run Projection

```bash
curl http://127.0.0.1:8001/agent/runs/{run_id}/projection | jq .
```

### Phase Debugging

```bash
# Inspect a phase trace
curl http://127.0.0.1:8001/debug/runs/{run_id}/phases/synthesis/trace | jq .

# Dry-run a phase (no persistence)
curl -X POST http://127.0.0.1:8001/debug/phases/planning/dry-run \
  -H "Content-Type: application/json" \
  -d '{"query":"test topic"}'

# Set breakpoint before synthesis
curl -X POST http://127.0.0.1:8001/debug/runs/{run_id}/breakpoints \
  -H "Content-Type: application/json" \
  -d '{"phase":"synthesis"}'
```

## 5. Store Configuration

```env
# In apps/agent-python/.env
AGENT_CORE_STORE_BACKEND=memory    # In-memory (default for dev)
AGENT_CORE_STORE_BACKEND=sqlite    # SQLite persistence
AGENT_CORE_STORE_SQLITE_PATH=./data/agent_core_store.sqlite3
```

## 6. MCP Search Management

```bash
# Check status
curl http://127.0.0.1:3210/health

# Restart
npx open-websearch@latest serve --port 3210

# Test search directly
curl -s -X POST http://127.0.0.1:3210/search \
  -H "Content-Type: application/json" \
  -d '{"query":"AI agents","limit":3,"engines":["baidu"]}' | jq .
```

## 7. RAG (ChromaDB)

```bash
# Verify ChromaDB has stored evidence
python -c "
from packages.tools.rag.chroma_store import ChromaEvidenceStore
store = ChromaEvidenceStore('./data/chroma')
print(f'Stored documents: {store.count()}')
"
```

The RAG layer is optional — the agent works without it (just skips the retrieval and upsert phases).

## 8. Troubleshooting

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| `ModuleNotFoundError: No module named 'app'` | Wrong working directory | `cd apps/agent-python` before running |
| Agent returns `Internal Server Error` | Check uvicorn logs for traceback | Usually a config or import issue |
| `Evidence: 0` in response | MCP search not running or not reachable | `curl http://127.0.0.1:3210/health` |
| `LLM decomposition failed` in logs | LLM JSON parsing issue | Check API key, model availability |
| Java returns 502 | Python Agent not running | `curl http://127.0.0.1:8001/agent/health` |
| Port already in use | Previous process didn't exit | `lsof -i :8001` / `netstat -ano \| grep 8001` |
| H2 database locked | Multiple Java instances | Kill all Java processes, delete `data/deep_research.mv.db` |

## 9. Environment Variables

```env
# Required
DEEPSEEK_API_KEY=sk-...              # LLM API key

# Agent Core
AGENT_CORE_STORE_BACKEND=memory       # memory | sqlite
AGENT_CORE_STORE_SQLITE_PATH=./data/agent_core_store.sqlite3

# MCP Search
MCP_SEARCH_ENABLED=true
MCP_SEARCH_SERVER_URL=http://127.0.0.1:3210
MCP_SEARCH_DEFAULT_ENGINE=baidu      # baidu | sogou | bing

# RAG
CHROMA_DB_PATH=./data/chroma
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5

# Java
JWT_SECRET=change-me-in-production
DB_PASSWORD=deepresearch
```

## 10. Git Hygiene

Do NOT commit:
- `apps/agent-python/.env`
- `*.log`, `logs/`
- `data/*.sqlite3`, `data/chroma/`
- `apps/api-java/data/`
- `node_modules/`, `dist/`, `target/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`
