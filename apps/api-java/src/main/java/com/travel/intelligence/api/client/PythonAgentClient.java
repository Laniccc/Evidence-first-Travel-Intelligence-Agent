package com.travel.intelligence.api.client;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PythonAgentClient {

    private final RestClient restClient;

    public PythonAgentClient(RestClient pythonAgentRestClient) {
        this.restClient = pythonAgentRestClient;
    }

    public JsonNode travelQuery(JsonNode requestBody) {
        return restClient.post()
                .uri("/agent/query")
                .contentType(MediaType.APPLICATION_JSON)
                .body(requestBody)
                .retrieve()
                .body(JsonNode.class);
    }
}
