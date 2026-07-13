package com.travel.intelligence.api.tool.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.travel.intelligence.api.tool.dto.ToolCallRequest;
import com.travel.intelligence.api.tool.config.ToolGatewayProperties;
import com.travel.intelligence.api.tool.dto.ToolCallResult;
import com.travel.intelligence.api.tool.dto.ToolTraceDto;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ToolGatewayServiceTest {

    @Test
    void searchMcpUnavailableWhenSearchDisabled() {
        ToolGatewayProperties props = new ToolGatewayProperties();
        props.setEnabled(true);
        props.setMcpEnabled(true);
        ToolGatewayProperties.SearchMcp search = new ToolGatewayProperties.SearchMcp();
        search.setEnabled(false);
        search.setServerUrl("http://localhost:9000");
        props.setSearch(search);

        ToolGatewayService service = new ToolGatewayService(props, new FakeSearchPort(false));

        assertFalse(service.isToolConfigured("search_mcp"));

        var result = service.call(new ToolCallRequest("search_mcp", Map.of("query", "kyoto"), null, null, null, null));

        assertFalse(result.ok());
        assertTrue(result.error().contains("MCP_SEARCH_ENABLED=false"));
    }

    @Test
    void openmeteoMcpStillUsesMockGateway() {
        ToolGatewayProperties props = new ToolGatewayProperties();
        props.setEnabled(true);
        props.setMcpEnabled(false);
        ToolGatewayService service = new ToolGatewayService(props, new FakeSearchPort(false));

        var result = service.call(new ToolCallRequest("openmeteo_mcp", Map.of(), null, null, null, null));

        assertTrue(result.ok());
        assertTrue(result.evidence().isEmpty());
        assertEquals("openmeteo_mcp", result.toolTrace().toolName());
    }

    @Test
    void unknownToolReturnsError() {
        ToolGatewayProperties props = new ToolGatewayProperties();
        ToolGatewayService service = new ToolGatewayService(props, new FakeSearchPort(false));

        var result = service.call(new ToolCallRequest("nope", Map.of(), null, null, null, null));

        assertFalse(result.ok());
        assertEquals("error", result.toolTrace().status());
    }

    private record FakeSearchPort(boolean configured) implements ToolSearchPort {

        @Override
        public String toolName() {
            return "search_mcp";
        }

        @Override
        public boolean isConfigured() {
            return configured;
        }

        @Override
        public ToolCallResult call(ToolCallRequest request) {
            return new ToolCallResult(
                    false,
                    List.of(),
                    new ToolTraceDto("search_mcp", "error", 1L, List.of(), configurationError(), request.arguments(), List.of()),
                    configurationError(),
                    "search_mcp",
                    request.callId());
        }

        private String configurationError() {
            return "search_mcp not configured: MCP_ENABLED=true, MCP_SEARCH_ENABLED=false, MCP_SEARCH_SERVER_URL=<empty>";
        }
    }
}
