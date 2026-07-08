package com.travel.intelligence.api.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.travel.intelligence.api.HealthController;
import com.travel.intelligence.api.session.TravelQueryService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.ResourceAccessException;

@WebMvcTest(controllers = {TravelProxyController.class, HealthController.class})
class TravelProxyControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private TravelQueryService travelQueryService;

    @Test
    void travelQueryProxiesToAgent() throws Exception {
        when(travelQueryService.travelQuery(any()))
                .thenReturn(JsonNodeFactory.instance.objectNode()
                        .put("answer", "ok")
                        .put("query_id", "q-1")
                        .put("session_id", "s-1"));

        mockMvc.perform(post("/api/travel/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"Kyoto\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answer").value("ok"))
                .andExpect(jsonPath("$.session_id").value("s-1"));
    }

    @Test
    void travelQueryReturns502WhenAgentDown() throws Exception {
        when(travelQueryService.travelQuery(any()))
                .thenThrow(new ResourceAccessException("Connection refused"));

        mockMvc.perform(post("/api/travel/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"test\"}"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error").value("agent_unavailable"));
    }
}
