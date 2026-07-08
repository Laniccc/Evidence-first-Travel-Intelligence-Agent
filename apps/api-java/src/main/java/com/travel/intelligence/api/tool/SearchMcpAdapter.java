package com.travel.intelligence.api.tool;

import com.travel.intelligence.api.tool.dto.ToolCallRequest;
import com.travel.intelligence.api.tool.dto.ToolCallResult;
import com.travel.intelligence.api.tool.dto.ToolTraceDto;
import com.travel.intelligence.api.tool.mcp.McpHttpClient;
import com.travel.intelligence.api.tool.mcp.McpInvokeResult;
import com.travel.intelligence.api.tool.mcp.SearchMcpEvidenceMapper;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class SearchMcpAdapter {

    public static final String TOOL_NAME = "search_mcp";

    private final ToolGatewayProperties properties;
    private final McpHttpClient mcpHttpClient;
    private final SearchMcpEvidenceMapper evidenceMapper;

    public SearchMcpAdapter(
            ToolGatewayProperties properties,
            McpHttpClient mcpHttpClient,
            SearchMcpEvidenceMapper evidenceMapper) {
        this.properties = properties;
        this.mcpHttpClient = mcpHttpClient;
        this.evidenceMapper = evidenceMapper;
    }

    public boolean isConfigured() {
        if (!properties.isMcpEnabled()) {
            return false;
        }
        ToolGatewayProperties.SearchMcp search = properties.getSearch();
        if (search == null || !search.isEnabled()) {
            return false;
        }
        String url = search.getServerUrl();
        return url != null && !url.isBlank();
    }

    public ToolCallResult call(ToolCallRequest request) {
        long started = System.nanoTime();
        Map<String, Object> arguments = request.arguments() != null ? request.arguments() : Map.of();

        if (!isConfigured()) {
            long latencyMs = elapsedMs(started);
            String error = configurationError();
            return new ToolCallResult(
                    false,
                    List.of(),
                    errorTrace(TOOL_NAME, latencyMs, arguments, error),
                    error,
                    TOOL_NAME,
                    request.callId());
        }

        ToolGatewayProperties.SearchMcp search = properties.getSearch();
        String mcpTool = search.getToolName();
        McpInvokeResult invoke = mcpHttpClient.invoke(
                search.getServerUrl(),
                mcpTool,
                arguments,
                properties.getMcpTimeoutSeconds());

        long latencyMs = Math.max(invoke.latencyMs(), elapsedMs(started));
        if (!invoke.ok()) {
            String error = invoke.error() != null ? invoke.error() : "MCP invoke failed";
            return new ToolCallResult(
                    false,
                    List.of(),
                    errorTrace(TOOL_NAME, latencyMs, arguments, error),
                    error,
                    TOOL_NAME,
                    request.callId());
        }

        var evidence = evidenceMapper.toEvidence(invoke.data(), arguments);
        if (evidence.isEmpty()) {
            String error = "MCP search returned no extractable evidence";
            return new ToolCallResult(
                    false,
                    List.of(),
                    errorTrace(TOOL_NAME, latencyMs, arguments, error),
                    error,
                    TOOL_NAME,
                    request.callId());
        }

        List<String> evidenceIds = evidence.stream().map(e -> e.evidenceId()).toList();
        ToolTraceDto trace = new ToolTraceDto(
                TOOL_NAME,
                "ok",
                latencyMs,
                evidenceIds,
                null,
                arguments,
                List.of("mcp_server=search"));

        return new ToolCallResult(true, evidence, trace, null, TOOL_NAME, request.callId());
    }

    private String configurationError() {
        ToolGatewayProperties.SearchMcp search = properties.getSearch();
        boolean searchEnabled = search != null && search.isEnabled();
        String url = search != null ? search.getServerUrl() : "";
        return "search_mcp not configured: MCP_ENABLED="
                + properties.isMcpEnabled()
                + ", MCP_SEARCH_ENABLED="
                + searchEnabled
                + ", MCP_SEARCH_SERVER_URL="
                + (url == null || url.isBlank() ? "<empty>" : url);
    }

    private static ToolTraceDto errorTrace(
            String toolName, long latencyMs, Map<String, Object> input, String error) {
        return new ToolTraceDto(toolName, "error", latencyMs, List.of(), error, input, List.of());
    }

    private static long elapsedMs(long startedNanos) {
        return Math.max(1L, (System.nanoTime() - startedNanos) / 1_000_000L);
    }
}
