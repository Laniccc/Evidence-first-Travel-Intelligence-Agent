package com.travel.intelligence.api.agent.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.travel.intelligence.api.agent.domain.SessionMemory;
import com.travel.intelligence.api.agent.infrastructure.InMemorySessionMemoryStore;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class TravelQueryServiceTest {

    @Mock
    private PythonAgentGateway pythonAgentGateway;

    private InMemorySessionMemoryStore store;
    private TravelQueryService service;

    @BeforeEach
    void setUp() {
        store = new InMemorySessionMemoryStore();
        service = new TravelQueryService(pythonAgentGateway, store);
    }

    @Test
    void injectsStoredMemoryOnSecondTurn() {
        when(pythonAgentGateway.query(any())).thenReturn(result(Map.of(
                "answer", "Kanas is suitable in summer.",
                "session_id", "sess-1",
                "query_id", "q-1")));

        service.travelQuery(new AgentQueryCommand(
                "When should I visit Kanas Lake?",
                "sess-1",
                false,
                Map.of()));

        when(pythonAgentGateway.query(any())).thenReturn(result(Map.of(
                "answer", "It is usually less crowded on weekdays.",
                "session_id", "sess-1",
                "query_id", "q-2")));

        service.travelQuery(new AgentQueryCommand(
                "Is it crowded there?",
                "sess-1",
                false,
                Map.of()));

        ArgumentCaptor<AgentQueryCommand> captor = ArgumentCaptor.forClass(AgentQueryCommand.class);
        verify(pythonAgentGateway, times(2)).query(captor.capture());
        AgentQueryCommand forwarded = captor.getAllValues().get(1);
        Map<?, ?> conversationMemory = (Map<?, ?>) forwarded.userContext().get("conversation_memory");
        assertEquals("When should I visit Kanas Lake?", conversationMemory.get("last_query"));
        assertTrue(conversationMemory.get("last_places").toString().contains("Kanas Lake"));

        SessionMemory saved = store.get("sess-1").orElseThrow();
        assertEquals("Is it crowded there?", saved.lastQuery());
        assertNotNull(saved.recentTurnsSummary());
    }

    @Test
    void generatesSessionIdWhenMissing() {
        when(pythonAgentGateway.query(any())).thenReturn(result(Map.of("answer", "ok")));

        AgentQueryResult response = service.travelQuery(new AgentQueryCommand("test", null, false, Map.of()));
        assertNotNull(response.sessionId());
        assertTrue(store.get(response.sessionId()).isPresent());
    }

    @Test
    void preservesAgentContractResponseFields() {
        when(pythonAgentGateway.query(any())).thenReturn(result(contractResponse()));

        AgentQueryResult response = service.travelQuery(new AgentQueryCommand(
                "Give me the evidence",
                "sess-contract",
                true,
                Map.of("party", List.of("family"))));

        assertEquals("Evidence-backed answer", response.answer());
        assertEquals("sess-contract", response.sessionId());
        assertEquals("query-contract", response.queryId());
        assertEquals("understood", response.visibleTrace().get(0));
        assertEquals("https://example.test/source", ((Map<?, ?>) response.evidenceSummary().get(0)).get("source_url"));
        assertEquals("sample limitation", response.limitations().get(0));
        assertEquals(0.91, response.confidence());
        assertEquals("search_mcp", ((Map<?, ?>) response.toolTraces().get(0)).get("tool_name"));
        assertEquals("Kanas Lake", ((Map<?, ?>) ((List<?>) response.structuredResult().get("places")).get(0)).get("place_name"));
        assertEquals("answer", ((Map<?, ?>) response.fieldEvidenceSummary().get(0)).get("field"));
        assertEquals("date_conflict", ((Map<?, ?>) response.conflicts().get(0)).get("type"));
        assertEquals("ok", response.citationCheckResult().get("status"));
        assertEquals("Kanas Lake", response.semanticFrameSummary().get("primary_place"));
        assertEquals("summary", response.answerMode());

        ArgumentCaptor<AgentQueryCommand> captor = ArgumentCaptor.forClass(AgentQueryCommand.class);
        verify(pythonAgentGateway).query(captor.capture());
        AgentQueryCommand forwarded = captor.getValue();
        assertEquals("Give me the evidence", forwarded.query());
        assertEquals("sess-contract", forwarded.sessionId());
        assertTrue(forwarded.debug());
        assertEquals(List.of("family"), forwarded.userContext().get("party"));
    }

    private static AgentQueryResult result(Map<String, Object> rawResponse) {
        return AgentQueryResult.fromRawResponse(rawResponse);
    }

    private static Map<String, Object> contractResponse() {
        return Map.ofEntries(
                Map.entry("answer", "Evidence-backed answer"),
                Map.entry("session_id", "sess-contract"),
                Map.entry("query_id", "query-contract"),
                Map.entry("confidence", 0.91),
                Map.entry("visible_trace", List.of("understood", "planned")),
                Map.entry("evidence_summary", List.of(Map.of("source_url", "https://example.test/source"))),
                Map.entry("limitations", List.of("sample limitation")),
                Map.entry("tool_traces", List.of(Map.of("tool_name", "search_mcp", "status", "ok"))),
                Map.entry("structured_result", Map.of("places", List.of(Map.of("place_name", "Kanas Lake")))),
                Map.entry("field_evidence_summary", List.of(Map.of("field", "answer"))),
                Map.entry("conflicts", List.of(Map.of("type", "date_conflict"))),
                Map.entry("citation_check_result", Map.of("status", "ok")),
                Map.entry("semantic_frame_summary", Map.of(
                        "primary_place", "Kanas Lake",
                        "city", "Altay",
                        "country", "China")),
                Map.entry("answer_mode", "summary"));
    }
}
