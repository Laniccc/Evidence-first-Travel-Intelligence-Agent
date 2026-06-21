package com.travel.intelligence.api.session;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.travel.intelligence.api.client.PythonAgentClient;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class TravelQueryServiceTest {

    @Mock
    private PythonAgentClient pythonAgentClient;

    private InMemorySessionMemoryStore store;
    private TravelQueryService service;
    private final ObjectMapper mapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        store = new InMemorySessionMemoryStore();
        service = new TravelQueryService(pythonAgentClient, store);
    }

    @Test
    void injectsStoredMemoryOnSecondTurn() throws Exception {
        ObjectNode firstResponse = mapper.createObjectNode()
                .put("answer", "秋季适合")
                .put("session_id", "sess-1")
                .put("query_id", "q-1");
        when(pythonAgentClient.travelQuery(any())).thenReturn(firstResponse);

        ObjectNode firstRequest = mapper.createObjectNode()
                .put("query", "喀纳斯湖适合几月份去")
                .put("session_id", "sess-1");
        service.travelQuery(firstRequest);

        ObjectNode secondAgentResponse = mapper.createObjectNode()
                .put("answer", "秋天人较多")
                .put("session_id", "sess-1")
                .put("query_id", "q-2");
        when(pythonAgentClient.travelQuery(any())).thenReturn(secondAgentResponse);

        ObjectNode secondRequest = mapper.createObjectNode()
                .put("query", "这里秋天人多吗")
                .put("session_id", "sess-1");
        service.travelQuery(secondRequest);

        ArgumentCaptor<JsonNode> captor = ArgumentCaptor.forClass(JsonNode.class);
        verify(pythonAgentClient, times(2)).travelQuery(captor.capture());
        JsonNode forwarded = captor.getAllValues().get(1);
        JsonNode conversationMemory = forwarded.path("user_context").path("conversation_memory");
        assertEquals("喀纳斯湖适合几月份去", conversationMemory.path("last_query").asText());
        assertTrue(conversationMemory.path("last_places").toString().contains("喀纳斯湖"));

        SessionMemory saved = store.get("sess-1").orElseThrow();
        assertEquals("这里秋天人多吗", saved.lastQuery());
        assertNotNull(saved.recentTurnsSummary());
    }

    @Test
    void generatesSessionIdWhenMissing() throws Exception {
        when(pythonAgentClient.travelQuery(any())).thenReturn(mapper.createObjectNode().put("answer", "ok"));

        JsonNode response = service.travelQuery(mapper.createObjectNode().put("query", "test"));
        assertNotNull(response.get("session_id"));
        assertTrue(store.get(response.get("session_id").asText()).isPresent());
    }
}
