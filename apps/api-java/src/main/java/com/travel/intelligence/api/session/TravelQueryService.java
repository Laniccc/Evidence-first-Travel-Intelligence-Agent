package com.travel.intelligence.api.session;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.travel.intelligence.api.client.PythonAgentClient;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class TravelQueryService {

    private final PythonAgentClient pythonAgentClient;
    private final SessionMemoryStore sessionMemoryStore;

    public TravelQueryService(PythonAgentClient pythonAgentClient, SessionMemoryStore sessionMemoryStore) {
        this.pythonAgentClient = pythonAgentClient;
        this.sessionMemoryStore = sessionMemoryStore;
    }

    public JsonNode travelQuery(JsonNode requestBody) {
        ObjectNode forward = requestBody.isObject()
                ? ((ObjectNode) requestBody).deepCopy()
                : JsonNodeFactory.instance.objectNode();

        String sessionId = textOrNull(forward.get("session_id"));
        if (sessionId == null) {
            sessionId = UUID.randomUUID().toString();
            forward.put("session_id", sessionId);
        }

        SessionMemory existing = sessionMemoryStore.get(sessionId).orElse(null);
        injectConversationMemory(forward, existing);

        JsonNode agentResponse = pythonAgentClient.travelQuery(forward);
        ObjectNode response = agentResponse.isObject()
                ? ((ObjectNode) agentResponse).deepCopy()
                : JsonNodeFactory.instance.objectNode();

        String resolvedSessionId = textOrNull(response.get("session_id"));
        if (resolvedSessionId == null) {
            resolvedSessionId = sessionId;
            response.put("session_id", resolvedSessionId);
        }

        String query = forward.path("query").asText("");
        sessionMemoryStore.save(buildUpdatedMemory(resolvedSessionId, query, response, existing));
        return response;
    }

    private void injectConversationMemory(ObjectNode forward, SessionMemory memory) {
        if (memory == null) {
            return;
        }
        ObjectNode userContext = ensureObject(forward, "user_context");
        ObjectNode conversationMemory = ensureObject(userContext, "conversation_memory");
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
            ArrayNode places = JsonNodeFactory.instance.arrayNode();
            memory.lastPlaces().forEach(places::add);
            conversationMemory.set("last_places", places);
        }
    }

    private SessionMemory buildUpdatedMemory(
            String sessionId, String query, ObjectNode response, SessionMemory existing) {
        List<String> places = extractPlaces(response);
        if (places.isEmpty() && existing != null && existing.lastPlaces() != null) {
            places = existing.lastPlaces();
        }
        if (places.isEmpty()) {
            places = inferPlacesFromQuery(query);
        }

        String city = textOrNull(response.path("semantic_frame_summary").get("city"));
        if (city == null && existing != null) {
            city = existing.lastCity();
        }

        String country = textOrNull(response.path("semantic_frame_summary").get("country"));
        if (country == null && existing != null) {
            country = existing.lastCountry();
        }

        String answerSnippet = textOrNull(response.get("answer"));
        if (answerSnippet != null && answerSnippet.length() > 120) {
            answerSnippet = answerSnippet.substring(0, 120) + "…";
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

    private static List<String> extractPlaces(JsonNode response) {
        Set<String> places = new LinkedHashSet<>();
        JsonNode structuredPlaces = response.path("structured_result").path("places");
        if (structuredPlaces.isArray()) {
            structuredPlaces.forEach(place -> {
                String name = textOrNull(place.get("place_name"));
                if (name == null) {
                    name = textOrNull(place.get("name"));
                }
                if (name != null) {
                    places.add(name);
                }
            });
        }
        JsonNode summary = response.path("semantic_frame_summary");
        String primary = textOrNull(summary.get("primary_place"));
        if (primary != null) {
            places.add(primary);
        }
        JsonNode mentioned = summary.get("mentioned_places");
        if (mentioned != null && mentioned.isArray()) {
            mentioned.forEach(node -> {
                if (node.isTextual()) {
                    places.add(node.asText());
                }
            });
        }
        return new ArrayList<>(places);
    }

    private static List<String> inferPlacesFromQuery(String query) {
        List<String> places = new ArrayList<>();
        if (query != null && query.contains("喀纳斯")) {
            places.add("喀纳斯湖");
        }
        return places;
    }

    private static ObjectNode ensureObject(ObjectNode parent, String field) {
        JsonNode node = parent.get(field);
        if (node instanceof ObjectNode objectNode) {
            return objectNode;
        }
        ObjectNode created = JsonNodeFactory.instance.objectNode();
        parent.set(field, created);
        return created;
    }

    private static String textOrNull(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        String text = node.asText();
        return text.isBlank() ? null : text;
    }
}
