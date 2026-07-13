# Runbook

## Ports

| Component | Port | Notes |
| --- | ---: | --- |
| Web | 5173 | Vite dev server |
| Java Platform API | 8082 | Spring Boot, auth, conversations, gateway |
| Python Agent | 8001 | FastAPI Agent runtime |
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

`apps/api-java/.env.example` is a template. Export those variables in your shell or set them in the IDE run configuration when you want to override defaults.

## Environment

Java Platform API:

```powershell
$env:SERVER_PORT="8082"
$env:APP_DB_URL="jdbc:h2:file:./data/api-java-db;AUTO_SERVER=TRUE;MODE=PostgreSQL"
$env:APP_JWT_SECRET="dev-change-me-to-a-long-random-secret-before-sharing"
$env:PYTHON_AGENT_BASE_URL="http://127.0.0.1:8001"
$env:TOOL_GATEWAY_ENABLED="true"
```

Python Agent:

```powershell
copy apps\agent-python\.env.example apps\agent-python\.env
```

Set at least one supported LLM key in `apps/agent-python/.env` before starting the Agent. Tool and MCP provider variables are also configured there. The Java Tool Gateway URL used by Python should point at the Java API when Python delegates tool calls back to Java.

Web:

```powershell
copy apps\web\.env.example apps\web\.env
```

Vite proxies `/api` to the Java Platform API during local development.

## Architecture Boundaries

Java Platform API uses domain-first layering. Runtime code should stay under the
`user`, `platform`, `agent`, `tool`, `common`, and `infrastructure.security`
domains, with controllers in `web`, use cases in `application`, business state in
`domain`, and persistence or external clients in `infrastructure`.

Python Agent uses product capability layers: `api`, `contracts`, `context`,
`understanding`, `planning`, `execution`, `tools`, `integrations`, `evidence`,
`composition`, `orchestration`, `governance`, and `observability`. The Agent API
keeps HTTP handling at the edge and delegates one Agent run through orchestration.

The Java-Agent boundary is intentionally narrow. Java owns users, authentication,
conversations, query records, favorites, profiles, and future billing or
subscriptions. Python owns a single Agent run and returns intelligence fields such
as `answer`, `session_id`, `query_id`, `confidence`, `evidence_summary`,
`tool_traces`, `visible_trace`, `limitations`, and `structured_result`.

### Retired Python Paths

The completed Agent consolidation removed `app.agents`, `app.orchestrator`,
`app.schemas`, `app.tool_gateway`, `app.storage`, `app.catalog`, `app.prompts`,
and `app.policies`. Do not import or recreate them. New Python behavior belongs in
the capability owner listed above. The only retained compatibility module is
`app.contract`, a contracts-only re-export for the public request/response models.

When a Java-Python request or response field changes, update both service owners
and run Python contract coverage plus Java client/platform-flow coverage before
changing the web client.

## Start

Python Agent:

```powershell
cd apps/agent-python
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Java Platform API:

```powershell
cd apps/api-java
mvn spring-boot:run
```

Web:

```powershell
cd apps/web
npm run dev
```

## Platform Smoke Test

Register:

```powershell
curl.exe -s -X POST http://127.0.0.1:8082/api/auth/register `
  -H "Content-Type: application/json" `
  -d '{"username":"demo","email":"demo@example.com","password":"secret123","displayName":"Demo User"}'
```

Use the returned token:

```powershell
$token = "paste-token-here"
```

Create a conversation:

```powershell
curl.exe -s -X POST http://127.0.0.1:8082/api/platform/conversations `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{"title":"Kyoto family trip"}'
```

Ask the Travel Agent:

```powershell
curl.exe -s -X POST http://127.0.0.1:8082/api/platform/conversations/1/query `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json; charset=utf-8" `
  -d '{"query":"京都清水寺适合带父母去吗？","userContext":{"party":["elderly"]}}'
```

## Verify

```powershell
cd apps/api-java
mvn test

cd ..\web
npm run build

cd ..\agent-python
python -m compileall app -q
python -m pytest tests -q
```

## Data

- Java local DB: `apps/api-java/data/`
- Python debug file: `apps/agent-python/debug_last_session.md`
- Web build output: `apps/web/dist/`
- Java build output: `apps/api-java/target/`

All of the above are local artifacts and ignored by Git.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Web cannot login | Confirm Java API is running on `:8082`; Vite proxies `/api` to Java. |
| Agent query times out | Confirm Python Agent is running on `:8001`; complex evidence queries can take longer. |
| `401 unauthorized` | Login again and refresh the token. |
| H2 console cannot open | Confirm Java API is running and `H2_CONSOLE_ENABLED=true`. |
| Need a clean H2 database | Stop Java, delete `apps/api-java/data/`, then restart Java. |
| Python Agent cannot call Java Tool Gateway | Confirm Java API is running on `:8082`, `TOOL_GATEWAY_ENABLED=true`, and the Python `.env` Java gateway URL points to Java. |
| Java returns `agent_unavailable` | Confirm `PYTHON_AGENT_BASE_URL` points to the running Python Agent and `/agent/health` is healthy. |
| `/agent/query` returns `405` in browser | Use `POST`; direct browser `GET` is expected to fail. |
| `open-webSearch did not become healthy` on first start | The first `npx` provisioning run can exceed 45 seconds. The scripts now wait up to 90 seconds; retry `.\scripts\start-agent.ps1` or use `-McpStartupTimeoutSec 120` on a slow network. Confirm `http://127.0.0.1:3210/health` returns `200` before using `-AllowMcpFailure`. |
