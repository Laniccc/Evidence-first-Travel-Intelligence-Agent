package com.travel.intelligence.api.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.travel.intelligence.api.client.PythonAgentClient;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClientException;

@RestController
@RequestMapping("/api/travel")
public class TravelProxyController {

    private final PythonAgentClient pythonAgentClient;

    public TravelProxyController(PythonAgentClient pythonAgentClient) {
        this.pythonAgentClient = pythonAgentClient;
    }

    @PostMapping("/query")
    public ResponseEntity<JsonNode> travelQuery(@RequestBody JsonNode requestBody) {
        try {
            return ResponseEntity.ok(pythonAgentClient.travelQuery(requestBody));
        } catch (RestClientException ex) {
            return agentUnavailable(ex);
        }
    }

    @GetMapping("/supported-regions")
    public ResponseEntity<JsonNode> supportedRegions() {
        try {
            return ResponseEntity.ok(pythonAgentClient.supportedRegions());
        } catch (RestClientException ex) {
            return agentUnavailable(ex);
        }
    }

    private ResponseEntity<JsonNode> agentUnavailable(Exception ex) {
        JsonNode body = JsonNodeFactory.instance.objectNode()
                .put("error", "python_agent_unavailable")
                .put("message", ex.getMessage());
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY).body(body);
    }
}
