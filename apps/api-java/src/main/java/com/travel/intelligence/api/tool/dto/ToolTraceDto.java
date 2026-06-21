package com.travel.intelligence.api.tool.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

public record ToolTraceDto(
        @JsonProperty("tool_name") String toolName,
        String status,
        @JsonProperty("latency_ms") long latencyMs,
        @JsonProperty("evidence_ids") List<String> evidenceIds,
        String error,
        Map<String, Object> input,
        List<String> limitations) {
}
