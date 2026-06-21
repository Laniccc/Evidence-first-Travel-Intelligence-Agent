package com.travel.intelligence.api.web;

import com.travel.intelligence.api.session.SessionMemory;
import com.travel.intelligence.api.session.SessionMemoryStore;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/session")
public class SessionMemoryController {

    private final SessionMemoryStore sessionMemoryStore;

    public SessionMemoryController(SessionMemoryStore sessionMemoryStore) {
        this.sessionMemoryStore = sessionMemoryStore;
    }

    @GetMapping("/{sessionId}/memory")
    public ResponseEntity<?> getMemory(@PathVariable String sessionId) {
        return sessionMemoryStore.get(sessionId)
                .<ResponseEntity<?>>map(memory -> ResponseEntity.ok(toDebugMap(memory)))
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND)
                        .body(Map.of("error", "session_not_found", "session_id", sessionId)));
    }

    @DeleteMapping("/{sessionId}/memory")
    public ResponseEntity<Map<String, Object>> deleteMemory(@PathVariable String sessionId) {
        boolean deleted = sessionMemoryStore.delete(sessionId);
        if (!deleted) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(Map.of("deleted", false, "session_id", sessionId));
        }
        return ResponseEntity.ok(Map.of("deleted", true, "session_id", sessionId));
    }

    private static Map<String, Object> toDebugMap(SessionMemory memory) {
        return Map.of(
                "session_id", memory.sessionId(),
                "last_query", memory.lastQuery() != null ? memory.lastQuery() : "",
                "last_places", memory.lastPlaces() != null ? memory.lastPlaces() : List.of(),
                "last_city", memory.lastCity() != null ? memory.lastCity() : "",
                "last_country", memory.lastCountry() != null ? memory.lastCountry() : "",
                "recent_turns_summary", memory.recentTurnsSummary() != null ? memory.recentTurnsSummary() : "",
                "updated_at", memory.updatedAt().toString());
    }
}
