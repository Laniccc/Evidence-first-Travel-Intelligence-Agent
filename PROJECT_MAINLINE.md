# Project Mainline

## Product Boundary

This repository is a travel intelligence platform. The Java service owns platform
business data and workflows; the Python service owns one evidence-first Agent run;
and the web application provides the authenticated user workspace.

```text
Web browser
  -> Java Platform API
     -> user/platform services and persisted conversations/query records
     -> agent application service
        -> PythonAgentClient -> Python POST /agent/query
           -> AgentRunService -> orchestration state machine
              -> understanding -> planning -> execution/integrations
              -> evidence -> composition -> AgentQueryResponse
```

## Ownership

- Java owns users, authentication, conversations, query history, favorites,
  profiles, and future commercial platform concerns.
- Python owns request understanding, research planning, tool execution, evidence
  evaluation, answer composition, run governance, and run observability.
- `packages/tools` contains shared Python tool implementations and imports final
  Agent capability owners directly.
- The web application calls Java platform endpoints only. It does not call the
  Python Agent directly.

## Contract Flow

1. The web client sends `query`, `userContext`, and `debug` to
   `POST /api/platform/conversations/{id}/query`.
2. Java converts the command to the Python contract fields `query`, `session_id`,
   `user_context`, and `debug` and calls `POST /agent/query`.
3. Python returns `AgentQueryResponse`; Java persists the original response and
   returns it as the `agentResponse` field beside the platform query record.
4. The web client renders the response and can retrieve the persisted response at
   `GET /api/platform/records/{id}/response`.

## Non-Negotiable Rules

- Every factual answer must be backed by `Evidence` with source URLs.
- New Python code belongs in a final capability layer, never a retired package.
- New Java code is placed by domain, then by `web`, `application`, `domain`, or
  `infrastructure` responsibility.
- Java-Python contract changes require Python contract tests and Java
  client/platform-flow tests before a web behavior change.

See [REPO_MAP.md](REPO_MAP.md) for the concrete runtime files and [RUNBOOK.md](RUNBOOK.md) for local operations.
