package com.travel.intelligence.api.platform;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.travel.intelligence.api.agent.application.AgentQueryCommand;
import com.travel.intelligence.api.agent.application.AgentQueryResult;
import com.travel.intelligence.api.agent.infrastructure.PythonAgentClient;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class TravelPlatformFlowTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockitoBean
    private PythonAgentClient pythonAgentClient;

    @ParameterizedTest
    @ValueSource(strings = {"safe_failure", "failed"})
    void terminalAgentFailureRemainsAStoredBusinessResponse(String terminal) throws Exception {
        when(pythonAgentClient.query(any())).thenReturn(AgentQueryResult.fromRawResponse(Map.of(
            "answer", "当前证据不足", "query_id", "safe-query", "confidence", 0.0,
            "orchestration_summary", Map.of("run_id", "safe-run", "terminal_state", terminal))));
        String registration = mockMvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
            .content(objectMapper.writeValueAsString(Map.of("username", "user_" + terminal,
                "email", terminal + "@example.test", "password", "fixture123", "displayName", "Safe Demo"))))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        String token = objectMapper.readTree(registration).path("token").asText();
        String conversation = mockMvc.perform(post("/api/platform/conversations")
            .header("Authorization", "Bearer " + token).contentType(MediaType.APPLICATION_JSON)
            .content("{\"title\":\"safe response\"}"))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        long id = objectMapper.readTree(conversation).path("id").asLong();
        String query = mockMvc.perform(post("/api/platform/conversations/{id}/query", id)
            .header("Authorization", "Bearer " + token).contentType(MediaType.APPLICATION_JSON)
            .content("{\"query\":\"颐和园地址\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.agentResponse.orchestration_summary.terminal_state").value(terminal))
            .andExpect(jsonPath("$.agentResponse.promotion_summary").doesNotExist())
            .andReturn().getResponse().getContentAsString();
        long recordId = objectMapper.readTree(query).path("record").path("id").asLong();
        mockMvc.perform(get("/api/platform/records/{id}/response", recordId)
            .header("Authorization", "Bearer " + token))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orchestration_summary.terminal_state").value(terminal));
    }

    @Test
    void userCanRegisterCreateConversationAndAskTravelAgent() throws Exception {
        ObjectNode agentResponse = JsonNodeFactory.instance.objectNode()
                .put("answer", "Kiyomizu-dera is suitable for families, but expect stairs.")
                .put("session_id", "agent-session")
                .put("query_id", "q-1")
                .put("confidence", 0.82)
                .put("answer_mode", "summary");
        agentResponse.set("visible_trace", JsonNodeFactory.instance.arrayNode().add("evidence_checked"));
        agentResponse.set("promotion_summary", JsonNodeFactory.instance.objectNode().put("status", "published").put("published_count", 1));
        agentResponse.set("index_sync_status", JsonNodeFactory.instance.objectNode().put("status", "pending").put("pending_count", 1));
        agentResponse.set("evidence_summary", JsonNodeFactory.instance.arrayNode()
                .add(JsonNodeFactory.instance.objectNode().put("source_url", "https://example.test/official")));
        agentResponse.set("limitations", JsonNodeFactory.instance.arrayNode().add("stairs may be difficult"));
        agentResponse.set("tool_traces", JsonNodeFactory.instance.arrayNode()
                .add(JsonNodeFactory.instance.objectNode().put("tool_name", "search_mcp").put("status", "ok")));
        agentResponse.set("structured_result", JsonNodeFactory.instance.objectNode()
                .set("places", JsonNodeFactory.instance.arrayNode()
                        .add(JsonNodeFactory.instance.objectNode().put("place_name", "Kiyomizu-dera"))));
        agentResponse.set("semantic_frame_summary", JsonNodeFactory.instance.objectNode()
                .put("primary_place", "Kiyomizu-dera")
                .put("city", "Kyoto")
                .put("country", "Japan"));
        Map<String, Object> rawAgentResponse = objectMapper.convertValue(agentResponse, new com.fasterxml.jackson.core.type.TypeReference<>() {
        });
        when(pythonAgentClient.query(any())).thenReturn(AgentQueryResult.fromRawResponse(rawAgentResponse));

        String registerJson = mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "intern_demo",
                                  "email": "intern@example.com",
                                  "password": "secret123",
                                  "displayName": "Intern Demo"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user.username").value("intern_demo"))
                .andReturn()
                .getResponse()
                .getContentAsString();
        String token = objectMapper.readTree(registerJson).path("token").asText();

        String conversationJson = mockMvc.perform(post("/api/platform/conversations")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Kyoto family trip\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Kyoto family trip"))
                .andReturn()
                .getResponse()
                .getContentAsString();
        Long conversationId = objectMapper.readTree(conversationJson).path("id").asLong();
        String agentSessionId = objectMapper.readTree(conversationJson).path("agentSessionId").asText();

        String askJson = mockMvc.perform(post("/api/platform/conversations/{id}/query", conversationId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "query": "Is Kiyomizu-dera suitable for parents?",
                                  "userContext": {"party": ["elderly"]}
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.record.query").value("Is Kiyomizu-dera suitable for parents?"))
                .andExpect(jsonPath("$.agentResponse.answer").value("Kiyomizu-dera is suitable for families, but expect stairs."))
                .andExpect(jsonPath("$.agentResponse.query_id").value("q-1"))
                .andExpect(jsonPath("$.agentResponse.promotion_summary.status").value("published"))
                .andExpect(jsonPath("$.agentResponse.index_sync_status.status").value("pending"))
                .andExpect(jsonPath("$.agentResponse.evidence_summary[0].source_url").value("https://example.test/official"))
                .andReturn()
                .getResponse()
                .getContentAsString();
        Long recordId = objectMapper.readTree(askJson).path("record").path("id").asLong();

        mockMvc.perform(get("/api/platform/conversations/{id}", conversationId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.records[0].confidence").value(0.82));

        mockMvc.perform(get("/api/platform/records/{recordId}/response", recordId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.session_id").value(agentSessionId))
                .andExpect(jsonPath("$.promotion_summary.published_count").value(1))
                .andExpect(jsonPath("$.index_sync_status.status").value("pending"))
                .andExpect(jsonPath("$.visible_trace[0]").value("evidence_checked"))
                .andExpect(jsonPath("$.limitations[0]").value("stairs may be difficult"))
                .andExpect(jsonPath("$.tool_traces[0].tool_name").value("search_mcp"))
                .andExpect(jsonPath("$.structured_result.places[0].place_name").value("Kiyomizu-dera"))
                .andExpect(jsonPath("$.semantic_frame_summary.primary_place").value("Kiyomizu-dera"));

        ArgumentCaptor<AgentQueryCommand> payloadCaptor = ArgumentCaptor.forClass(AgentQueryCommand.class);
        verify(pythonAgentClient).query(payloadCaptor.capture());
        AgentQueryCommand forwarded = payloadCaptor.getValue();
        org.assertj.core.api.Assertions.assertThat(forwarded.query())
                .isEqualTo("Is Kiyomizu-dera suitable for parents?");
        org.assertj.core.api.Assertions.assertThat(forwarded.sessionId()).isNotBlank();
        org.assertj.core.api.Assertions.assertThat(forwarded.sessionId()).isEqualTo(agentSessionId);
        org.assertj.core.api.Assertions.assertThat(((java.util.List<?>) forwarded.userContext().get("party")).get(0))
                .isEqualTo("elderly");
    }
}
