package com.travel.intelligence.api.tool.infrastructure.mcp;

import java.util.Map;

public interface McpHttpClient {

    McpInvokeResult invoke(String serverUrl, String toolName, Map<String, Object> arguments, int timeoutSeconds);
}
