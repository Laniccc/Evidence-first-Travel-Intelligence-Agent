package com.travel.intelligence.api.tool;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.travel.intelligence.api.tool.dto.ClaimDto;
import com.travel.intelligence.api.tool.dto.ToolCallRequest;
import com.travel.intelligence.api.tool.mcp.McpHttpClient;
import com.travel.intelligence.api.tool.mcp.McpInvokeResult;
import com.travel.intelligence.api.tool.mcp.SearchMcpEvidenceMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class SearchMcpAdapterTest {

    @Test
    void searchMcpNotConfiguredReturnsExplicitError() {
        ToolGatewayProperties props = baseProperties(false, false, "");
        SearchMcpAdapter adapter = new SearchMcpAdapter(props, mockClient(), new SearchMcpEvidenceMapper());

        assertFalse(adapter.isConfigured());

        var result = adapter.call(new ToolCallRequest("search_mcp", Map.of("query", "kanas"), null, null, null, null));

        assertFalse(result.ok());
        assertTrue(result.error().contains("search_mcp not configured"));
        assertTrue(result.error().contains("MCP_SEARCH_ENABLED=false"));
        assertEquals("error", result.toolTrace().status());
        assertTrue(result.toolTrace().latencyMs() >= 1);
    }

    @Test
    void searchMcpDisabledWhenOnlyGlobalMcpEnabled() {
        ToolGatewayProperties props = baseProperties(true, false, "http://localhost:9000");
        SearchMcpAdapter adapter = new SearchMcpAdapter(props, mockClient(), new SearchMcpEvidenceMapper());

        assertFalse(adapter.isConfigured());
    }

    @Test
    void mockMcpClientReturnsStructuredEvidence() {
        ToolGatewayProperties props = baseProperties(true, true, "http://localhost:9000");
        McpHttpClient client = (url, tool, args, timeout) -> McpInvokeResult.success(
                Map.of(
                        "results",
                        List.of(Map.of(
                                "title", "Kanas Lake travel guide",
                                "snippet", "Best months: June–September for mild weather.",
                                "url", "https://example.com/kanas"))),
                5L);

        SearchMcpAdapter adapter = new SearchMcpAdapter(props, client, new SearchMcpEvidenceMapper());

        assertTrue(adapter.isConfigured());

        var result = adapter.call(new ToolCallRequest(
                "search_mcp",
                Map.of("query", "喀纳斯湖适合几月份去", "information_need", "best_time_to_visit"),
                null,
                null,
                null,
                null));

        assertTrue(result.ok());
        assertEquals(1, result.evidence().size());
        assertEquals("search_mcp", result.evidence().getFirst().sourceName());
        assertFalse(result.evidence().getFirst().claims().isEmpty());
        ClaimDto claim = result.evidence().getFirst().claims().getFirst();
        assertEquals("best_time_to_visit", claim.claimType());
        assertTrue(String.valueOf(claim.value()).contains("June"));
        assertEquals("ok", result.toolTrace().status());
        assertEquals(1, result.toolTrace().evidenceIds().size());
        assertTrue(result.toolTrace().latencyMs() >= 1);
    }

    private static ToolGatewayProperties baseProperties(boolean mcpEnabled, boolean searchEnabled, String url) {
        ToolGatewayProperties props = new ToolGatewayProperties();
        props.setEnabled(true);
        props.setMcpEnabled(mcpEnabled);
        props.setMcpTimeoutSeconds(10);
        ToolGatewayProperties.SearchMcp search = new ToolGatewayProperties.SearchMcp();
        search.setEnabled(searchEnabled);
        search.setServerUrl(url);
        search.setToolName("public_web_search");
        props.setSearch(search);
        return props;
    }

    private static McpHttpClient mockClient() {
        return (url, tool, args, timeout) -> McpInvokeResult.failure("should not be called", 1L);
    }
}
