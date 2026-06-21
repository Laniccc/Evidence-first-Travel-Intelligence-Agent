package com.travel.intelligence.api.web;

import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.travel.intelligence.api.client.PythonAgentClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClientException;

@RestController
public class AgentHealthController {

    private final PythonAgentClient pythonAgentClient;

    public AgentHealthController(PythonAgentClient pythonAgentClient) {
        this.pythonAgentClient = pythonAgentClient;
    }

    @GetMapping("/health/agent")
    public Map<String, Object> agentHealth() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("service", "api-java");
        try {
            JsonNode agent = pythonAgentClient.agentHealth();
            result.put("python_agent", "up");
            result.put("python_agent_health", agent);
        } catch (RestClientException ex) {
            result.put("python_agent", "down");
            result.put("message", ex.getMessage());
        }
        return result;
    }
}
