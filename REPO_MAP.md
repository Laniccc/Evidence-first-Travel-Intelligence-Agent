# Repository Map

## Runtime Entrypoints

| Area | Entry Point | Responsibility |
| --- | --- | --- |
| Python Agent | `apps/agent-python/app/main.py` | FastAPI application entrypoint |
| Python HTTP API | `apps/agent-python/app/api/routes.py` | `/agent/health` and `/agent/query` |
| Python run coordinator | `apps/agent-python/app/orchestration/state_machine.py` | Agent state flow |
| Java platform | `apps/api-java/src/main/java/com/travel/intelligence/api/ApiJavaApplication.java` | Spring Boot application |
| Java-Python gateway | `apps/api-java/src/main/java/com/travel/intelligence/api/agent/infrastructure/PythonAgentClient.java` | Python Agent HTTP client |
| Web client | `apps/web/src/main.js` | Platform workspace UI |
| Web API client | `apps/web/src/api/travel.js` | Authenticated Java API requests |

## Python Capability Owners

| Package | Owns |
| --- | --- |
| `api` | FastAPI routes, lifespan, and HTTP error boundaries |
| `contracts` | Java-Python request, response, and error contracts |
| `context` | Conversation context and memory |
| `understanding` | Intent, entities, semantic frame, and travel-task extraction |
| `planning` | Information needs, research plans, and source/tool selection |
| `execution` | Tool scheduling, retries, fallback, and execution state |
| `tools` | Agent-owned tool abstractions and MCP integration setup |
| `integrations` | Java gateway, storage, catalog, LLM, and external clients |
| `evidence` | Evidence quality, source policy, coverage, conflicts, and citations |
| `composition` | Answer drafting, response shaping, prompts, and sanitization |
| `orchestration` | State machine and run coordination |
| `governance` | Safety, quality gates, budgets, and failure reasons |
| `observability` | Logs, traces, and debug-session artifacts |

## Java Domains

| Domain | Layers | Responsibility |
| --- | --- | --- |
| `user` | `domain`, `application`, `infrastructure`, `web` | Accounts, authentication, and principals |
| `platform` | `domain`, `application`, `infrastructure`, `web` | Conversations, query records, favorites, and platform flow |
| `agent` | `domain`, `application`, `infrastructure`, `web`, `config` | Agent commands, session memory, and Python integration |
| `tool` | `application`, `infrastructure`, `web`, `config`, `dto` | Java tool gateway and MCP-facing adapters |
| `common` / `infrastructure.security` | cross-cutting | API errors, exception mapping, JWT, and security |

## Retired Surfaces

Do not import or recreate these deleted Python packages: `app.agents`,
`app.orchestrator`, `app.schemas`, `app.tool_gateway`, `app.storage`,
`app.catalog`, `app.prompts`, and `app.policies`.

`app.contract` is intentionally retained as a tiny public re-export of
`app.contracts.request.AgentQueryRequest` and
`app.contracts.response.AgentQueryResponse`. It is not a general-purpose facade.

## Verification Targets

- Python contracts: `apps/agent-python/tests/test_agent_contract_layer.py`
- Python runtime/layering: `apps/agent-python/tests/`
- Java Agent contract: `apps/api-java/src/test/java/com/travel/intelligence/api/agent/application/TravelQueryServiceTest.java`
- Java platform flow: `apps/api-java/src/test/java/com/travel/intelligence/api/platform/TravelPlatformFlowTest.java`
- Web build: `npm run build` from `apps/web`
