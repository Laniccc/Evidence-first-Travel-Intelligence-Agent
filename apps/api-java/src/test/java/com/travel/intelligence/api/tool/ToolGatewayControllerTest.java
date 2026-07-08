package com.travel.intelligence.api.tool;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.travel.intelligence.api.tool.dto.ToolCallResult;
import com.travel.intelligence.api.tool.dto.ToolTraceDto;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = ToolGatewayController.class)
class ToolGatewayControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private ToolGatewayService toolGatewayService;

    @BeforeEach
    void setUp() {
        when(toolGatewayService.isGatewayEnabled()).thenReturn(true);
    }

    @Test
    void callSearchMcpReturnsMockResult() throws Exception {
        when(toolGatewayService.call(any())).thenReturn(new ToolCallResult(
                true,
                List.of(),
                new ToolTraceDto("search_mcp", "ok", 2L, List.of(), null, Map.of("q", "kyoto"), List.of("mock")),
                null,
                "search_mcp",
                null));

        mockMvc.perform(post("/internal/tools/call")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"tool_name\":\"search_mcp\",\"arguments\":{\"q\":\"kyoto\"}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true))
                .andExpect(jsonPath("$.evidence").isArray())
                .andExpect(jsonPath("$.tool_trace.tool_name").value("search_mcp"))
                .andExpect(jsonPath("$.tool_trace.status").value("ok"))
                .andExpect(jsonPath("$.tool_trace.latency_ms").value(2));
    }

    @Test
    void unknownToolReturnsError() throws Exception {
        when(toolGatewayService.call(any())).thenReturn(new ToolCallResult(
                false,
                List.of(),
                new ToolTraceDto("unknown_tool", "error", 1L, List.of(), "unknown tool_name: unknown_tool", Map.of(), List.of()),
                "unknown tool_name: unknown_tool",
                "unknown_tool",
                null));

        mockMvc.perform(post("/internal/tools/call")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"tool_name\":\"unknown_tool\",\"arguments\":{}}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.ok").value(false))
                .andExpect(jsonPath("$.error").value("unknown tool_name: unknown_tool"))
                .andExpect(jsonPath("$.tool_trace.status").value("error"));
    }
}
