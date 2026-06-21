package com.travel.intelligence.api.session;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class InMemorySessionMemoryStore implements SessionMemoryStore {

    private final ConcurrentHashMap<String, SessionMemory> store = new ConcurrentHashMap<>();

    @Override
    public Optional<SessionMemory> get(String sessionId) {
        if (sessionId == null || sessionId.isBlank()) {
            return Optional.empty();
        }
        return Optional.ofNullable(store.get(sessionId));
    }

    @Override
    public void save(SessionMemory memory) {
        store.put(memory.sessionId(), memory);
    }

    @Override
    public boolean delete(String sessionId) {
        if (sessionId == null || sessionId.isBlank()) {
            return false;
        }
        return store.remove(sessionId) != null;
    }
}
