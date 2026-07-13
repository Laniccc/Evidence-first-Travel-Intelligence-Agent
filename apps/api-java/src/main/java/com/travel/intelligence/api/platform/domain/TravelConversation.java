package com.travel.intelligence.api.platform.domain;

import java.time.Instant;
import java.util.UUID;

public class TravelConversation {

    private Long id;
    private Long userId;
    private String title;
    private String agentSessionId = UUID.randomUUID().toString();
    private ConversationStatus status = ConversationStatus.ACTIVE;
    private Instant createdAt = Instant.now();
    private Instant updatedAt = Instant.now();

    public TravelConversation(Long userId, String title) {
        this(null, userId, title, UUID.randomUUID().toString(), ConversationStatus.ACTIVE, Instant.now(), Instant.now());
    }

    public TravelConversation(
            Long id,
            Long userId,
            String title,
            String agentSessionId,
            ConversationStatus status,
            Instant createdAt,
            Instant updatedAt) {
        this.id = id;
        this.userId = userId;
        this.title = normalizeTitle(title);
        this.agentSessionId = agentSessionId != null ? agentSessionId : UUID.randomUUID().toString();
        this.status = status != null ? status : ConversationStatus.ACTIVE;
        this.createdAt = createdAt != null ? createdAt : Instant.now();
        this.updatedAt = updatedAt != null ? updatedAt : this.createdAt;
    }

    public Long getId() {
        return id;
    }

    public Long getUserId() {
        return userId;
    }

    public String getTitle() {
        return title;
    }

    public String getAgentSessionId() {
        return agentSessionId;
    }

    public ConversationStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void rename(String title) {
        this.title = normalizeTitle(title);
        touch();
    }

    public void archive() {
        this.status = ConversationStatus.ARCHIVED;
        touch();
    }

    public void touch() {
        this.updatedAt = Instant.now();
    }

    private static String normalizeTitle(String title) {
        String normalized = title != null && !title.isBlank() ? title.trim() : "New travel plan";
        return normalized.length() > 120 ? normalized.substring(0, 120) : normalized;
    }
}
