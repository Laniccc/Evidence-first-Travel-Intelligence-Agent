package com.travel.intelligence.api.agent.infrastructure;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.travel.intelligence.api.agent.application.AgentQueryCommand;
import com.travel.intelligence.api.agent.application.AgentQueryResult;
import com.travel.intelligence.api.agent.application.PythonAgentGateway;
import com.travel.intelligence.api.agent.config.AgentProperties;
import com.travel.intelligence.api.common.ApiException;
import com.travel.intelligence.api.common.ApplicationErrorCode;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@Service
public class PythonAgentClient implements PythonAgentGateway {

    private final RestClient restClient;
    private final ObjectMapper objectMapper;
    private final AgentProperties properties;

    public PythonAgentClient(
            RestClient pythonAgentRestClient,
            ObjectMapper objectMapper,
            AgentProperties properties) {
        this.restClient = pythonAgentRestClient;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    @Override
    public AgentQueryResult query(AgentQueryCommand command) {
        try {
            String traceId = textOrGenerated(command.traceId());
            RestClient.RequestBodySpec request = restClient.post()
                    .uri("/agent/query")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("X-Trace-Id", traceId);
            if (properties.getServiceKey() != null && !properties.getServiceKey().isBlank()) {
                request.header("X-Agent-Service-Key", properties.getServiceKey());
            }
            JsonNode response = request.body(toRequestBody(command))
                    .retrieve()
                    .body(JsonNode.class);
            return AgentQueryResult.fromRawResponse(toMap(response));
        } catch (ResourceAccessException ex) {
            if (isTimeout(ex)) {
                throw new ApiException(ApplicationErrorCode.AGENT_TIMEOUT, message(ex, "Travel Agent timed out"));
            }
            throw new ApiException(ApplicationErrorCode.AGENT_UNAVAILABLE, message(ex, "Travel Agent unavailable"));
        } catch (RestClientResponseException ex) {
            if (ex.getStatusCode() == HttpStatus.UNAUTHORIZED) {
                throw new ApiException(
                        ApplicationErrorCode.AGENT_UNAUTHORIZED,
                        "Python Agent rejected the service credential");
            }
            throw new ApiException(ApplicationErrorCode.AGENT_ERROR, message(ex, "Travel Agent returned an error"));
        } catch (RestClientException ex) {
            throw new ApiException(ApplicationErrorCode.AGENT_UNAVAILABLE, message(ex, "Travel Agent unavailable"));
        }
    }

    private static String textOrGenerated(String value) {
        return value != null && !value.isBlank() ? value : UUID.randomUUID().toString();
    }

    private ObjectNode toRequestBody(AgentQueryCommand command) {
        ObjectNode body = objectMapper.createObjectNode();
        if (command.query() != null) {
            body.put("query", command.query());
        }
        if (command.sessionId() != null) {
            body.put("session_id", command.sessionId());
        }
        body.put("debug", command.debug());
        if (!command.userContext().isEmpty()) {
            body.set("user_context", objectMapper.valueToTree(command.userContext()));
        }
        return body;
    }

    private Map<String, Object> toMap(JsonNode response) {
        if (response == null || !response.isObject()) {
            return Map.of();
        }
        return objectMapper.convertValue(response, new TypeReference<>() {
        });
    }

    private static boolean isTimeout(ResourceAccessException ex) {
        String message = ex.getMessage() != null ? ex.getMessage().toLowerCase() : "";
        return message.contains("timed out") || message.contains("timeout");
    }

    private static String message(Exception ex, String fallback) {
        return ex.getMessage() != null && !ex.getMessage().isBlank() ? ex.getMessage() : fallback;
    }
}
