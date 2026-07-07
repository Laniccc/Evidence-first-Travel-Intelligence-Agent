# Deep Research Agent Platform

> Evidence-first autonomous research agent — Java Spring Boot business backend + Python AI engine.

Submit any research topic → the Agent **plans** a search strategy, **searches the web** in real time, **fetches and reads** pages, **extracts claims** via LLM, **cross-references** facts, and produces a **structured report with citations** and source quality grades.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Vue 3 + TypeScript (:3000)                                 │
│  Research query UI → real-time phase progress → report view │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST (JWT Bearer)
┌──────────────────────▼──────────────────────────────────────┐
│  Java Spring Boot 3.4 (:8082)                               │
│  Auth (JWT+BCrypt) │ Project CRUD (JPA) │ Agent Proxy       │
│  H2 (dev) / PostgreSQL (prod) │ Flyway migrations           │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP (localhost)
┌──────────────────────▼──────────────────────────────────────┐
│  Python Agent — FastAPI (:8001)                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  6-Phase Pipeline + 7 Quality Gates                  │    │
│  │  planning → knowledge_retrieval → evidence_acq       │    │
│  │  → evidence_extraction → synthesis → knowledge_upsert│    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌──────────────┐ ┌───────────────┐ ┌──────────────────┐    │
│  │ MCP Search   │ │ DeepSeek LLM  │ │ ChromaDB (RAG)   │    │
│  │ (open-       │ │ (Anthropic    │ │ (bge-small-      │    │
│  │  websearch)  │ │  SDK, v4)     │ │  zh-v1.5)        │    │
│  └──────────────┘ └───────────────┘ └──────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Quickstart

### Prerequisites

- Python 3.11+
- Java 21 + Maven 3.9
- Node.js 20+
- DeepSeek API key ([platform.deepseek.com](https://platform.deepseek.com))

### 1. Configure

```bash
cp .env.example apps/agent-python/.env
# Edit apps/agent-python/.env → add DEEPSEEK_API_KEY=sk-...
```

### 2. Start MCP Search

```bash
npm install -g open-websearch
open-websearch serve --port 3210
# Verify: curl http://127.0.0.1:3210/health
```

### 3. Start Services

```bash
# Terminal 1 — Python Agent
cd apps/agent-python
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Terminal 2 — Java Backend
cd apps/api-java
mvn spring-boot:run

# Terminal 3 — Frontend (dev)
cd apps/web
npm install && npm run dev
```

### 4. Verify

```bash
curl http://127.0.0.1:8001/agent/health   # Python Agent
curl http://127.0.0.1:8082/api/health      # Java Backend
curl http://127.0.0.1:3000                 # Frontend
```

## One-Click (Docker)

```bash
docker compose up
# Starts: python-agent (:8001) + java-backend (:8082)
```

## Agent Pipeline

```
POST /agent/query
  │
  ├─ Gate 1: Input        ← safety filter, researchability check
  ├─ Phase 1: Planning    ← LLM decomposes topic → 2–5 sub-questions
  ├─ Phase 2: Knowledge Retrieval ← ChromaDB semantic search for existing evidence
  ├─ Phase 3: Evidence Acquisition ← MCP web search (Baidu/Bing/Sogou)
  ├─ Gate 3: Source       ← discard Tier-5 spam, ensure Tier-3+ sources
  ├─ Phase 4: Evidence Extraction ← fetch pages + LLM claim extraction
  ├─ Gate 4: Evidence     ← gap detection → auto retry search
  ├─ Gate 5: Cross-Ref    ← core claims need 2+ independent sources
  ├─ Phase 5: Synthesis   ← LLM composes structured report with [N] citations
  ├─ Gate 6: Citation     ← every factual claim must have URL reference
  ├─ Phase 6: Knowledge Upsert ← new evidence vectorized → ChromaDB
  └─ Gate 7: Delivery     ← completeness check → degraded if partial
```

### Source Quality Tiers

| Tier | Examples | Confidence | Behavior |
|------|----------|------------|----------|
| 1 | arxiv.org, *.gov.cn, official docs | 0.90 | Priority adoption |
| 2 | infoq.cn, Stack Overflow, tech blogs | 0.75 | Primary source |
| 3 | zhihu.com (high votes), juejin.cn | 0.55 | Usable |
| 4 | Personal blogs, forums | 0.35 | Needs cross-ref |
| 5 | Content farms, SEO spam | 0.00 | **Discarded** |

## API

### Register & Login

```bash
curl -X POST http://127.0.0.1:8082/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"a@b.com","password":"demo123"}'

# → {"token":"eyJ...", "userId":"...", "username":"demo"}
```

### Submit Research Query

```bash
TOKEN="..."  # from login above
curl -X POST http://127.0.0.1:8082/api/research/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What are the key trends in AI agents in 2025?"}'

# → {"status":"completed","run_id":"run_xxx","report":{...},"evidence_count":10,...}
```

### Direct Agent Query (bypass Java)

```bash
curl -X POST http://127.0.0.1:8001/agent/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Analyze the impact of transformer models on NLP"}'
```

### Debug Endpoints

```bash
# Phase introspection
GET  /debug/runs/{run_id}/phases/{phase_name}/trace

# Dry-run (execute without persisting)
POST /debug/phases/{phase_name}/dry-run

# Set breakpoint before a phase
POST /debug/runs/{run_id}/breakpoints
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vue 3 + TypeScript + Vite + Pinia |
| Java Backend | Spring Boot 3.4, Security + JWT, JPA, H2/PostgreSQL, Flyway |
| Python Agent | FastAPI, Anthropic SDK (DeepSeek v4), Pydantic v2 |
| Search | MCP open-websearch (Baidu/Sogou/Bing) |
| RAG | ChromaDB + BAAI/bge-small-zh-v1.5 |
| LLM | DeepSeek v4-flash (Anthropic-compatible API) |
| DevOps | Docker Compose, GitHub Actions CI |

## Project Structure

```
├── apps/
│   ├── agent-python/app/
│   │   ├── agent_core/          ← State-space Agent runtime
│   │   │   ├── state/           ← Run/Topic/Phase/Evidence models + lifecycle
│   │   │   ├── phases/          ← 6 phase implementations
│   │   │   ├── contracts/       ← Task contracts + 7 gate checks
│   │   │   ├── supervisor.py    ← Deterministic pipeline driver
│   │   │   └── store.py         ← Abstract Store + Memory/SQLite backends
│   │   ├── schemas/             ← Pydantic API models
│   │   ├── debug/               ← Phase introspection & replay endpoints
│   │   └── main.py              ← FastAPI entry point
│   ├── api-java/                ← Spring Boot business backend
│   └── web/                     ← Vue 3 SPA
├── packages/tools/
│   ├── mcp/                     ← MCP client manager + transport layer
│   └── rag/                     ← ChromaDB store + embedding service
├── docker-compose.yml
└── pyproject.toml
```

## Development

```bash
# Python — lint & type-check
cd apps/agent-python
pip install -e ".[dev]"
ruff check .
mypy app/

# Java — compile & test
cd apps/api-java
mvn compile
mvn test

# Frontend — dev server
cd apps/web
npm install && npm run dev
```

## Verified (2026-07-07)

| Check | Status |
|-------|--------|
| Python Agent starts (uvicorn :8001) | ✅ |
| Java Backend starts (Spring Boot :8082) | ✅ |
| MCP Search connected (:3210) | ✅ |
| Vue 3 Frontend builds | ✅ |
| LLM (DeepSeek v4) API calls | ✅ 7 calls/query |
| Web search + fetch + extract | ✅ real results |
| Report generation with citations | ✅ 10 sources, 5 limitations |
| JWT auth (register/login/proxy) | ✅ |
| 6-phase pipeline completes | ✅ |
| Docker Compose | ✅ |
| GitHub Actions CI | ✅ |
