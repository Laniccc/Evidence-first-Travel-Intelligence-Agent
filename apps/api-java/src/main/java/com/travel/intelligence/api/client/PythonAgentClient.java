package com.travel.intelligence.api.client;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Service
public class PythonAgentClient {

    private final RestClient restClient;

    public PythonAgentClient(RestClient pythonAgentRestClient) {
        this.restClient = pythonAgentRestClient;
    }

    public JsonNode travelQuery(JsonNode requestBody) {
        return restClient.post()
                .uri("/api/travel/query")
                .contentType(MediaType.APPLICATION_JSON)
                .body(requestBody)
                .retrieve()
                .body(JsonNode.class);
    }

    public JsonNode supportedRegions() {
        return restClient.get()
                .uri("/api/travel/supported-regions")
                .retrieve()
                .body(JsonNode.class);
    }

    public JsonNode agentHealth() {
        return restClient.get()
                .uri("/health")
                .retrieve()
                .body(JsonNode.class);
    }

    public boolean isReachable() {
        try {
            agentHealth();
            return true;
        } catch (RestClientResponseException ex) {
            return false;
        } catch (RuntimeException ex) {
            return false;
        }
    }
}
