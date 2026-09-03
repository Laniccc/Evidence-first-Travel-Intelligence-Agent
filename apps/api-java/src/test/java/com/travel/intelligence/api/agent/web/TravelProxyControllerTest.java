package com.travel.intelligence.api.agent.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.travel.intelligence.api.agent.application.AgentQueryResult;
import com.travel.intelligence.api.common.ApiException;
import com.travel.intelligence.api.common.ApplicationErrorCode;
import com.travel.intelligence.api.common.HealthController;
import com.travel.intelligence.api.infrastructure.security.JwtService;
import com.travel.intelligence.api.agent.application.TravelQueryService;
import java.util.Map;
import org.mockito.ArgumentCaptor;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = {TravelProxyController.class, HealthController.class})
@AutoConfigureMockMvc(addFilters = false)
class TravelProxyControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private TravelQueryService travelQueryService;

    @MockitoBean
    private JwtService jwtService;

    @Test
    void travelQueryProxiesToAgent() throws Exception {
        when(travelQueryService.travelQuery(any()))
                .thenReturn(AgentQueryResult.fromRawResponse(Map.of(
                        "answer", "ok",
                        "query_id", "q-1",
                        "session_id", "s-1")));

        mockMvc.perform(post("/api/travel/query")
                        .header("X-Trace-Id", "trace-proxy-1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"Kyoto\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answer").value("ok"))
                .andExpect(jsonPath("$.session_id").value("s-1"));

        ArgumentCaptor<com.travel.intelligence.api.agent.application.AgentQueryCommand> captor =
                ArgumentCaptor.forClass(com.travel.intelligence.api.agent.application.AgentQueryCommand.class);
        verify(travelQueryService).travelQuery(captor.capture());
        org.assertj.core.api.Assertions.assertThat(captor.getValue().traceId()).isEqualTo("trace-proxy-1");
    }

    @Test
    void travelQueryReturns502WhenAgentDown() throws Exception {
        when(travelQueryService.travelQuery(any()))
                .thenThrow(new ApiException(ApplicationErrorCode.AGENT_UNAVAILABLE, "Connection refused"));

        mockMvc.perform(post("/api/travel/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"test\"}"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("agent_unavailable"));
    }
}
