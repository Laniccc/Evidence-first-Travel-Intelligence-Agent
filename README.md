# Travel Agent Platform

一个面向 Java 全栈实习作品集的 Travel Agent 平台项目。Python FastAPI 提供 Evidence-first Travel Agent 能力，Java Spring Boot 负责用户、认证、会话、交互记录和 Agent Gateway，Web 提供平台工作台。

核心原则：事实性回答必须来自 `Evidence` 对象和来源 URL；Java 平台层负责用户与交互数据，Python Agent 层负责证据检索和回答生成。

## Features

- 用户注册、登录、JWT 鉴权
- Travel Agent 会话创建、列表、归档
- 用户提问记录持久化
- Agent 回答、置信度、trace、证据摘要保存
- 回答收藏与收藏列表
- Java Gateway 继续兼容旧 `/api/travel/query`
- Web 工作台：登录、会话、提问、历史、收藏、回答详情

## Verified Baseline

The current consolidated baseline has passed the full repository verification:

- Java: 23 tests via `mvn test`
- Python Agent: 57 tests via `python -m pytest`, plus FastAPI import smoke
- Web: Vite production build via `npm run build`
- Layering: retired Python-package and Java dependency scans return no matches

For the active request flow and package ownership, read [PROJECT_MAINLINE.md](PROJECT_MAINLINE.md) and [REPO_MAP.md](REPO_MAP.md).

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

Open http://127.0.0.1:5173/.

## Services

| Service | URL |
| --- | --- |
| Web platform | http://127.0.0.1:5173/ |
| Java API | http://127.0.0.1:8082/ |
| Python Agent health | http://127.0.0.1:8001/agent/health |
| H2 console | http://127.0.0.1:8082/h2-console |

## Java API Surface

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Register and return JWT |
| `POST` | `/api/auth/login` | Login and return JWT |
| `GET` | `/api/auth/me` | Current user |
| `GET` | `/api/platform/conversations` | List active conversations |
| `POST` | `/api/platform/conversations` | Create conversation |
| `GET` | `/api/platform/conversations/{id}` | Conversation detail and query records |
| `POST` | `/api/platform/conversations/{id}/query` | Ask Travel Agent and save result |
| `PUT` | `/api/platform/records/{id}/favorite` | Favorite/unfavorite answer |
| `GET` | `/api/platform/favorites` | List favorite answers |
| `POST` | `/api/travel/query` | Legacy direct Travel Agent proxy |

## Java-Agent Boundary

Java is the business platform. It owns users, authentication, conversations, query records, favorites, profile data, and future admin/billing/subscription concerns. Python owns one Agent run at a time: understand the travel question, plan evidence retrieval, call tools, evaluate evidence, compose the answer, and return trace/quality data.

Stable Agent endpoints:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| `GET` | `/agent/health` | Python Agent | Runtime health for Java/operator checks |
| `POST` | `/agent/query` | Python Agent | Java sends query, `session_id`, `user_context`, and debug flag |

Java stores these response fields in platform records where available: `answer`, `session_id`, `query_id`, `visible_trace`, `evidence_summary`, `limitations`, `confidence`, `tool_traces`, `structured_result`, `field_evidence_summary`, `conflicts`, `citation_check_result`, `semantic_frame_summary`, and `answer_mode`.

## Runtime Structure

```text
apps/agent-python/     Python Agent runtime
apps/api-java/         Java platform backend and gateway
apps/web/              Frontend platform workspace
packages/tools/        Shared Python tool implementations
contracts/schemas/     JSON schema contracts
scripts/               Runtime helper scripts
```

## Java Layering

`apps/api-java` uses domain-oriented layering:

```text
com.travel.intelligence.api
├── common                         shared API errors and exception handling
├── infrastructure.security        JWT, security filter, Spring Security config
├── user
│   ├── domain                     user entity, role, principal
│   ├── application                registration/login use cases
│   ├── infrastructure             user repositories
│   └── web                        auth controllers and request/response DTOs
├── platform
│   ├── domain                     conversations and query records
│   ├── application                Travel Agent platform use cases
│   ├── infrastructure             conversation/query repositories
│   └── web                        platform controllers and DTOs
├── agent
│   ├── application                Java-side Agent query orchestration
│   ├── domain                     short-term session memory contracts
│   ├── infrastructure             Python Agent client and memory store
│   ├── web                        legacy/proxy Agent endpoints
│   └── config                     Agent client configuration
└── tool
    ├── application                Java tool gateway use cases
    ├── infrastructure             MCP/search adapters
    ├── web                        internal tool gateway endpoint
    ├── config                     tool gateway properties
    └── dto                        tool contracts shared with Python Agent
```

Rule of thumb: controllers stay in `web`, business use cases stay in `application`, entities and business state stay in `domain`, and external systems or persistence stay in `infrastructure`.

Domain code does not depend on Spring or JPA. Persistence mappings, repositories, and external clients belong in `infrastructure`.

## Agent Product Capability Layers

The Python Agent is implemented with the following capability owners. Runtime code goes directly to the owner layer; these are not migration placeholders.

```text
apps/agent-python/app
|-- api                 FastAPI routes, health, lifecycle, HTTP error mapping
|-- contracts           Java-Python request/response/error models
|-- context             session context, conversation memory, preferences
|-- understanding       query understanding, intent, entities, SemanticFrame
|-- planning            research plan, information needs, tool selection, gaps
|-- execution           tool scheduling, retry/timeout/fallback, tool traces
|-- tools               Agent-owned tool abstractions
|-- integrations        Java gateway, MCP, LLM, weather, places, search adapters
|-- evidence            source quality, citation, coverage, conflict, evidence brief
|-- composition         answer composer, response contract, prompts, sanitizer
|-- orchestration       state machine, AgentRun, phase flow
|-- governance          cost, safety, tool budget, quality gates, failure reasons
`-- observability       logs, trace, debug session, metrics
```

Rule of thumb: `composition` consumes evidence but does not call tools; `execution` calls tools but does not write final answers; `orchestration` coordinates capability services instead of embedding detailed business rules.

### Retired Python Packages

The following packages were removed and must not be recreated or imported:

```text
app.agents
app.orchestrator
app.schemas
app.tool_gateway
app.storage
app.catalog
app.prompts
app.policies
```

`app.contract` remains only as a stable, contracts-only re-export of `AgentQueryRequest` and `AgentQueryResponse` for public API compatibility. It must not become a general compatibility layer or import retired packages.

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

## Configuration

```powershell
copy apps\agent-python\.env.example apps\agent-python\.env
copy apps\web\.env.example apps\web\.env
copy apps\api-java\.env.example apps\api-java\.env
```

Python and Web read local env files during normal development. For Java, use `apps/api-java/.env.example` as a template and export the variables in your shell or IDE run configuration before `mvn spring-boot:run`.

Java uses H2 by default:

```properties
APP_DB_URL=jdbc:h2:file:./data/api-java-db;AUTO_SERVER=TRUE;MODE=PostgreSQL
APP_JWT_SECRET=dev-change-me-to-a-long-random-secret-before-sharing
```

Local database files are ignored by Git.

See [RUNBOOK.md](RUNBOOK.md) for operations details.
