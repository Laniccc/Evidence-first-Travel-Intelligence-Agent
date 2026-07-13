package com.travel.intelligence.api.agent.domain;

import java.time.Instant;
import java.util.List;

public record SessionMemory(
        String sessionId,
        String lastQuery,
        List<String> lastPlaces,
        String lastCity,
        String lastCountry,
        String recentTurnsSummary,
        Instant updatedAt) {
}
