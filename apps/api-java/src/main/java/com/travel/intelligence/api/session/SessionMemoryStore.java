package com.travel.intelligence.api.session;

import java.util.Optional;

public interface SessionMemoryStore {

    Optional<SessionMemory> get(String sessionId);

    void save(SessionMemory memory);

    boolean delete(String sessionId);
}
