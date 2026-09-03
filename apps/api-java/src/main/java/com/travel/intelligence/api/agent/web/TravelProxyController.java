package com.travel.intelligence.api.agent.web;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.travel.intelligence.api.agent.application.AgentQueryCommand;
import com.travel.intelligence.api.agent.application.AgentQueryResult;
import com.travel.intelligence.api.agent.application.TravelQueryService;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/travel")
public class TravelProxyController {

    private final TravelQueryService travelQueryService;
    private final ObjectMapper objectMapper;

    public TravelProxyController(TravelQueryService travelQueryService, ObjectMapper objectMapper) {
        this.travelQueryService = travelQueryService;
        this.objectMapper = objectMapper;
    }

    @PostMapping("/query")
    public JsonNode travelQuery(
            @RequestBody JsonNode requestBody,
            @RequestHeader(value = "X-Trace-Id", required = false) String traceId) {
        AgentQueryResult result = travelQueryService.travelQuery(toCommand(requestBody).withTraceId(traceId));
        return objectMapper.valueToTree(result.rawResponse());
    }

    private AgentQueryCommand toCommand(JsonNode requestBody) {
        JsonNode userContext = requestBody.path("user_context");
        Map<String, Object> context = userContext.isObject()
                ? objectMapper.convertValue(userContext, new TypeReference<>() {
                })
                : Map.of();
        return new AgentQueryCommand(
                requestBody.path("query").asText(""),
                textOrNull(requestBody.get("session_id")),
                requestBody.path("debug").asBoolean(false),
                context);
    }

    private static String textOrNull(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        String text = node.asText();
        return text.isBlank() ? null : text;
    }
}
