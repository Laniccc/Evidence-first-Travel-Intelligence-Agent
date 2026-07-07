package com.deepresearch.api.agent;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

@Component
public class PythonAgentClient {

    private final RestTemplate restTemplate;
    private final ObjectMapper mapper = new ObjectMapper();

    public PythonAgentClient() {
        this.restTemplate = new RestTemplate();
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> submitQuery(String query, Map<String, Object> userContext) {
        try {
            Map<String, Object> payload = Map.of(
                "query", query,
                "user_context", userContext != null ? userContext : Map.of(),
                "debug", false
            );

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            HttpEntity<Map<String, Object>> request = new HttpEntity<>(payload, headers);

            ResponseEntity<Map> response = restTemplate.postForEntity(
                "http://127.0.0.1:8001/agent/query",
                request,
                Map.class
            );
            return response.getBody();
        } catch (Exception e) {
            return Map.of("status", "error", "message", e.getMessage());
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> getHealth() {
        try {
            return restTemplate.getForObject("http://127.0.0.1:8001/agent/health", Map.class);
        } catch (Exception e) {
            return Map.of("status", "error", "message", e.getMessage());
        }
    }
}
