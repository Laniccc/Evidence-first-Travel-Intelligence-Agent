package com.travel.intelligence.api.tool.application;

import com.travel.intelligence.api.tool.dto.ToolCallRequest;
import com.travel.intelligence.api.tool.dto.ToolCallResult;
import com.travel.intelligence.api.tool.dto.ToolTraceDto;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class ToolGatewayService {

    private static final Set<String> MOCK_TOOLS = Set.of("openmeteo_mcp", "osm_mcp");

    private final ToolGatewaySettings settings;
    private final ToolSearchPort searchPort;

    public ToolGatewayService(ToolGatewaySettings settings, ToolSearchPort searchPort) {
        this.settings = settings;
        this.searchPort = searchPort;
    }

    public ToolCallResult call(ToolCallRequest request) {
        String toolName = request.toolName();
        if (searchPort.toolName().equals(toolName)) {
            return searchPort.call(request);
        }
        if (MOCK_TOOLS.contains(toolName)) {
            return mockCall(request);
        }
        long latencyMs = 1L;
        return new ToolCallResult(
                false,
                List.of(),
                errorTrace(toolName, latencyMs, "unknown_tool: " + toolName),
                "unknown tool_name: " + toolName,
                toolName,
                request.callId());
    }

    public boolean isGatewayEnabled() {
        return settings.isEnabled();
    }

    public boolean isToolConfigured(String toolName) {
        if (searchPort.toolName().equals(toolName)) {
            return searchPort.isConfigured();
        }
        if (MOCK_TOOLS.contains(toolName)) {
            return settings.isMcpEnabled();
        }
        return false;
    }

    private ToolCallResult mockCall(ToolCallRequest request) {
        long started = System.nanoTime();
        String toolName = request.toolName();
        long latencyMs = elapsedMs(started);
        String limitation = "MCP mock gateway (" + toolName + "): MCP_ENABLED="
                + settings.isMcpEnabled() + " - no real evidence returned";
        ToolTraceDto trace = new ToolTraceDto(
                toolName,
                "ok",
                latencyMs,
                List.of(),
                null,
                request.arguments() != null ? request.arguments() : Map.of(),
                List.of(limitation));

        return new ToolCallResult(
                true,
                List.of(),
                trace,
                limitation,
                toolName,
                request.callId());
    }

    private static ToolTraceDto errorTrace(String toolName, long latencyMs, String error) {
        return new ToolTraceDto(toolName, "error", latencyMs, List.of(), error, Map.of(), List.of());
    }

    private static long elapsedMs(long startedNanos) {
        return Math.max(1L, (System.nanoTime() - startedNanos) / 1_000_000L);
    }
}
