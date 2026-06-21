package com.travel.intelligence.api.session;

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
