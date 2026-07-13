package com.travel.intelligence.api.agent.application;

import java.util.LinkedHashMap;
import java.util.Map;

public record AgentQueryCommand(
        String query,
        String sessionId,
        boolean debug,
        Map<String, Object> userContext
) {
    public AgentQueryCommand {
        userContext = userContext != null ? new LinkedHashMap<>(userContext) : Map.of();
    }

    public AgentQueryCommand withSessionId(String sessionId) {
        return new AgentQueryCommand(query, sessionId, debug, userContext);
    }

    public AgentQueryCommand withUserContext(Map<String, Object> userContext) {
        return new AgentQueryCommand(query, sessionId, debug, new LinkedHashMap<>(userContext));
    }
}
