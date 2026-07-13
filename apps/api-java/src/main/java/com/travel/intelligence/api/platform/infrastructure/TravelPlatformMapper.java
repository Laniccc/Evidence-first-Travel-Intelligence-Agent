package com.travel.intelligence.api.platform.infrastructure;

import com.travel.intelligence.api.platform.domain.TravelConversation;
import com.travel.intelligence.api.platform.domain.TravelQueryRecord;
import com.travel.intelligence.api.user.infrastructure.UserAccountEntity;

public final class TravelPlatformMapper {

    private TravelPlatformMapper() {
    }

    public static TravelConversation toDomain(TravelConversationEntity entity) {
        if (entity == null) {
            return null;
        }
        return new TravelConversation(
                entity.getId(),
                entity.getUser().getId(),
                entity.getTitle(),
                entity.getAgentSessionId(),
                entity.getStatus(),
                entity.getCreatedAt(),
                entity.getUpdatedAt());
    }

    public static TravelConversationEntity toEntity(TravelConversation conversation, UserAccountEntity user) {
        return new TravelConversationEntity(
                conversation.getId(),
                user,
                conversation.getTitle(),
                conversation.getAgentSessionId(),
                conversation.getStatus(),
                conversation.getCreatedAt(),
                conversation.getUpdatedAt());
    }

    public static TravelQueryRecord toDomain(TravelQueryRecordEntity entity) {
        if (entity == null) {
            return null;
        }
        return new TravelQueryRecord(
                entity.getId(),
                entity.getConversation().getId(),
                entity.getQueryText(),
                entity.getAnswerPreview(),
                entity.getConfidence(),
                entity.isFavorite(),
                entity.getResponseJson(),
                entity.getCreatedAt());
    }

    public static TravelQueryRecordEntity toEntity(TravelQueryRecord record, TravelConversationEntity conversation) {
        return new TravelQueryRecordEntity(
                record.getId(),
                conversation,
                record.getQueryText(),
                record.getAnswerPreview(),
                record.getConfidence(),
                record.isFavorite(),
                record.getResponseJson(),
                record.getCreatedAt());
    }
}
