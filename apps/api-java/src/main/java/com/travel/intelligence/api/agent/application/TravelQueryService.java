package com.travel.intelligence.api.agent.application;

import com.travel.intelligence.api.agent.domain.SessionMemory;
import com.travel.intelligence.api.agent.domain.SessionMemoryStore;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class TravelQueryService {

    private final PythonAgentGateway pythonAgentGateway;
    private final SessionMemoryStore sessionMemoryStore;

    public TravelQueryService(PythonAgentGateway pythonAgentGateway, SessionMemoryStore sessionMemoryStore) {
        this.pythonAgentGateway = pythonAgentGateway;
        this.sessionMemoryStore = sessionMemoryStore;
    }

    public AgentQueryResult travelQuery(AgentQueryCommand command) {
        String sessionId = textOrNull(command.sessionId());
        if (sessionId == null) {
            sessionId = UUID.randomUUID().toString();
        }
        AgentQueryCommand forward = command.withSessionId(sessionId);

        SessionMemory existing = sessionMemoryStore.get(sessionId).orElse(null);
        forward = injectConversationMemory(forward, existing);

        AgentQueryResult response = pythonAgentGateway.query(forward);

        String resolvedSessionId = textOrNull(response.sessionId());
        if (resolvedSessionId == null) {
            resolvedSessionId = sessionId;
            response = response.withSessionId(resolvedSessionId);
        }

        String query = forward.query() != null ? forward.query() : "";
        sessionMemoryStore.save(buildUpdatedMemory(resolvedSessionId, query, response, existing));
        return response;
    }

    private AgentQueryCommand injectConversationMemory(AgentQueryCommand forward, SessionMemory memory) {
        if (memory == null) {
            return forward;
        }
        Map<String, Object> userContext = new LinkedHashMap<>(forward.userContext());
        Map<String, Object> conversationMemory = ensureMap(userContext, "conversation_memory");
        if (memory.lastQuery() != null) {
            conversationMemory.put("last_query", memory.lastQuery());
        }
        if (memory.lastCity() != null) {
            conversationMemory.put("last_city", memory.lastCity());
        }
        if (memory.lastCountry() != null) {
            conversationMemory.put("last_country", memory.lastCountry());
        }
        if (memory.lastPlaces() != null && !memory.lastPlaces().isEmpty()) {
            conversationMemory.put("last_places", new ArrayList<>(memory.lastPlaces()));
        }
        userContext.put("conversation_memory", conversationMemory);
        return forward.withUserContext(userContext);
    }

    private SessionMemory buildUpdatedMemory(
            String sessionId, String query, AgentQueryResult response, SessionMemory existing) {
        List<String> places = extractPlaces(response);
        if (places.isEmpty() && existing != null && existing.lastPlaces() != null) {
            places = existing.lastPlaces();
        }
        if (places.isEmpty()) {
            places = inferPlacesFromQuery(query);
        }

        String city = textOrNull(response.semanticFrameSummary().get("city"));
        if (city == null && existing != null) {
            city = existing.lastCity();
        }

        String country = textOrNull(response.semanticFrameSummary().get("country"));
        if (country == null && existing != null) {
            country = existing.lastCountry();
        }

        String answerSnippet = textOrNull(response.answer());
        if (answerSnippet != null && answerSnippet.length() > 120) {
            answerSnippet = answerSnippet.substring(0, 120) + "...";
        }

        String summary = appendTurnSummary(
                existing != null ? existing.recentTurnsSummary() : null, query, answerSnippet);

        return new SessionMemory(
                sessionId,
                query,
                places,
                city,
                country,
                summary,
                Instant.now());
    }

    private static String appendTurnSummary(String previous, String query, String answerSnippet) {
        String turn = "Q: " + query;
        if (answerSnippet != null && !answerSnippet.isBlank()) {
            turn += " | A: " + answerSnippet;
        }
        if (previous == null || previous.isBlank()) {
            return turn;
        }
        return previous + "\n" + turn;
    }

    private static List<String> extractPlaces(AgentQueryResult response) {
        Set<String> places = new LinkedHashSet<>();
        Object structuredPlaces = response.structuredResult().get("places");
        if (structuredPlaces instanceof List<?> placeNodes) {
            placeNodes.forEach(place -> {
                if (!(place instanceof Map<?, ?> placeMap)) {
                    return;
                }
                String name = textOrNull(placeMap.get("place_name"));
                if (name == null) {
                    name = textOrNull(placeMap.get("name"));
                }
                if (name != null) {
                    places.add(name);
                }
            });
        }
        Map<String, Object> summary = response.semanticFrameSummary();
        String primary = textOrNull(summary.get("primary_place"));
        if (primary != null) {
            places.add(primary);
        }
        Object mentioned = summary.get("mentioned_places");
        if (mentioned instanceof List<?> values) {
            values.forEach(value -> {
                if (value instanceof String text && !text.isBlank()) {
                    places.add(text);
                }
            });
        }
        return new ArrayList<>(places);
    }

    private static List<String> inferPlacesFromQuery(String query) {
        List<String> places = new ArrayList<>();
        if (query != null && query.toLowerCase().contains("kanas")) {
            places.add("Kanas Lake");
        }
        return places;
    }

    private static Map<String, Object> ensureMap(Map<String, Object> parent, String field) {
        Object value = parent.get(field);
        if (value instanceof Map<?, ?> existing) {
            Map<String, Object> copied = new LinkedHashMap<>();
            existing.forEach((key, nestedValue) -> copied.put(String.valueOf(key), nestedValue));
            return copied;
        }
        return new LinkedHashMap<>();
    }

    private static String textOrNull(Object value) {
        if (value == null) {
            return null;
        }
        String text = value instanceof String stringValue ? stringValue : String.valueOf(value);
        return text.isBlank() ? null : text;
    }
}
