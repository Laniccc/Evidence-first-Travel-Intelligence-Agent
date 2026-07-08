package com.travel.intelligence.api.tool.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public record ToolCallResult(
        boolean ok,
        List<EvidenceDto> evidence,
        @JsonProperty("tool_trace") ToolTraceDto toolTrace,
        String error,
        @JsonProperty("tool_name") String toolName,
        @JsonProperty("call_id") String callId) {
}
