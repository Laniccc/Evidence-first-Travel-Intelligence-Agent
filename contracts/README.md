# Contracts — 跨语言通信协议

`contracts/` 是 **Java、Python、Web** 共用的 API 与核心数据契约来源。

## 原则

1. **单一真相源**：对外 HTTP 与网关层的请求/响应形状以 `contracts/schemas/*.schema.json` 为准。
2. **Python 可更丰富**：`apps/agent-python` 内 Pydantic 模型可包含额外字段（如 `structured_result`、`semantic_frame_summary`），但 **对外响应必须兼容** 本目录 schema（必填字段齐全、类型一致；额外字段允许存在）。
3. **Java 对齐 contracts**：`apps/api-java` 的 DTO 后续根据本目录 schema 生成或手写对齐，不另起一套协议。
4. **Web 对齐 contracts**：前端 TypeScript 类型或表单校验应引用同一 schema（或由其生成）。

## 目录

```
contracts/
├── README.md
└── schemas/
    ├── travel_query_request.schema.json   # POST /api/travel/query
    ├── travel_query_response.schema.json  # POST /api/travel/query
    ├── conversation_memory.schema.json    # user_context.conversation_memory
    ├── evidence.schema.json
    ├── tool_trace.schema.json
    ├── tool_call_request.schema.json      # Agent → tool
    └── tool_call_result.schema.json       # Tool → agent
```

## 最小对外面（Travel API）

### TravelQueryRequest

| 字段 | 必填 | 说明 |
|------|------|------|
| `query` | 是 | 用户自然语言问题 |
| `session_id` | 否 | 客户端会话 id |
| `user_context` | 否 | 用户画像 / 会话上下文（可含 `conversation_memory`） |
| `debug` | 否 | 是否返回扩展 trace |

### TravelQueryResponse（最小兼容集）

| 字段 | 必填 | 说明 |
|------|------|------|
| `answer` | 是 | 自然语言回答 |
| `session_id` | 否* | 会话 id（Python 实现中常见，建议返回） |
| `query_id` | 否* | 单次查询 id |
| `visible_trace` | 是 | 可见步骤 trace |
| `evidence_summary` | 是 | 证据摘要列表 |
| `limitations` | 是 | 限制与说明 |
| `confidence` | 是 | 0–1 置信度 |
| `tool_traces` | 是 | 工具调用 trace |

\* 当前 Pydantic 模型中为 optional，但建议在对外 API 中尽量返回。

## 版本

- Schema 格式：JSON Schema Draft **2020-12**
- 契约版本：在后续迭代中于各 `$id` 或独立 `version` 字段维护

## 参考实现（只读对照）

Pydantic 定义以 `apps/agent-python/app/schemas/` 为准，并遵守本 contracts。

## 校验（本地）

```bash
python -m json.tool contracts/schemas/travel_query_request.schema.json > /dev/null
# 安装 jsonschema 后可对样例 payload 做 validate
```
