package com.travel.intelligence.api.tool.mcp;

public record McpInvokeResult(boolean ok, Object data, String error, long latencyMs) {

    public static McpInvokeResult success(Object data, long latencyMs) {
        return new McpInvokeResult(true, data, null, latencyMs);
    }

    public static McpInvokeResult failure(String error, long latencyMs) {
        return new McpInvokeResult(false, null, error, latencyMs);
    }
}
