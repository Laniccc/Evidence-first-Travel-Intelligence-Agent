package com.deepresearch.api.agent;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/research")
public class AgentProxyController {

    private final PythonAgentClient agentClient;

    public AgentProxyController(PythonAgentClient agentClient) {
        this.agentClient = agentClient;
    }

    @PostMapping("/query")
    public ResponseEntity<?> query(@RequestBody Map<String, Object> payload) {
        String query = (String) payload.get("query");
        @SuppressWarnings("unchecked")
        Map<String, Object> userContext = (Map<String, Object>) payload.get("user_context");
        try {
            var result = agentClient.submitQuery(query, userContext);
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            return ResponseEntity.status(502).body(Map.of(
                "status", "error",
                "message", "Agent request failed: " + e.getMessage()
            ));
        }
    }
}
