package com.travel.intelligence.api.tool.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

public record ToolCallRequest(
        @JsonProperty("tool_name") String toolName,
        Map<String, Object> arguments,
        @JsonProperty("session_id") String sessionId,
        @JsonProperty("query_id") String queryId,
        @JsonProperty("trace_id") String traceId,
        @JsonProperty("call_id") String callId) {
}
