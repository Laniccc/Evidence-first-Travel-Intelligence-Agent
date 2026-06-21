package com.travel.intelligence.api.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.travel.intelligence.api.HealthController;
import com.travel.intelligence.api.client.PythonAgentClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.ResourceAccessException;

@WebMvcTest(controllers = {TravelProxyController.class, AgentHealthController.class, HealthController.class})
class TravelProxyControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private PythonAgentClient pythonAgentClient;

    @Test
    void travelQueryProxiesToPythonAgent() throws Exception {
        when(pythonAgentClient.travelQuery(any()))
                .thenReturn(JsonNodeFactory.instance.objectNode().put("answer", "ok"));

        mockMvc.perform(post("/api/travel/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"Kyoto in June\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.answer").value("ok"));
    }

    @Test
    void travelQueryReturnsBadGatewayWhenAgentDown() throws Exception {
        when(pythonAgentClient.travelQuery(any()))
                .thenThrow(new ResourceAccessException("connection refused"));

        mockMvc.perform(post("/api/travel/query")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"test\"}"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error").value("python_agent_unavailable"));
    }

    @Test
    void supportedRegionsProxiesToPythonAgent() throws Exception {
        var body = JsonNodeFactory.instance.objectNode();
        body.putArray("countries").add("Japan");
        when(pythonAgentClient.supportedRegions()).thenReturn(body);

        mockMvc.perform(get("/api/travel/supported-regions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.countries[0]").value("Japan"));
    }
}
