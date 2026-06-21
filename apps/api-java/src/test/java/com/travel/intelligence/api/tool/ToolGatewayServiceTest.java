package com.travel.intelligence.api.tool;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.travel.intelligence.api.tool.dto.ToolCallRequest;
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

        SearchMcpAdapter searchAdapter = new SearchMcpAdapter(
                props,
                (url, tool, args, timeout) -> null,
                new com.travel.intelligence.api.tool.mcp.SearchMcpEvidenceMapper());
        ToolGatewayService service = new ToolGatewayService(props, searchAdapter);

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
        SearchMcpAdapter searchAdapter = new SearchMcpAdapter(
                props,
                (url, tool, args, timeout) -> null,
                new com.travel.intelligence.api.tool.mcp.SearchMcpEvidenceMapper());
        ToolGatewayService service = new ToolGatewayService(props, searchAdapter);

        var result = service.call(new ToolCallRequest("openmeteo_mcp", Map.of(), null, null, null, null));

        assertTrue(result.ok());
        assertTrue(result.evidence().isEmpty());
        assertEquals("openmeteo_mcp", result.toolTrace().toolName());
    }

    @Test
    void unknownToolReturnsError() {
        ToolGatewayProperties props = new ToolGatewayProperties();
        SearchMcpAdapter searchAdapter = new SearchMcpAdapter(
                props,
                (url, tool, args, timeout) -> null,
                new com.travel.intelligence.api.tool.mcp.SearchMcpEvidenceMapper());
        ToolGatewayService service = new ToolGatewayService(props, searchAdapter);

        var result = service.call(new ToolCallRequest("nope", Map.of(), null, null, null, null));

        assertFalse(result.ok());
        assertEquals("error", result.toolTrace().status());
    }
}
