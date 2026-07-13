package com.travel.intelligence.api.platform.web.dto;

import com.travel.intelligence.api.platform.domain.ConversationStatus;
import com.travel.intelligence.api.platform.domain.TravelConversation;
import java.time.Instant;

public record ConversationSummary(
        Long id,
        String title,
        String agentSessionId,
        ConversationStatus status,
        Instant createdAt,
        Instant updatedAt
) {
    public static ConversationSummary from(TravelConversation conversation) {
        return new ConversationSummary(
                conversation.getId(),
                conversation.getTitle(),
                conversation.getAgentSessionId(),
                conversation.getStatus(),
                conversation.getCreatedAt(),
                conversation.getUpdatedAt());
    }
}
