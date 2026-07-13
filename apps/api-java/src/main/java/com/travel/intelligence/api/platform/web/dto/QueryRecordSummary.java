package com.travel.intelligence.api.platform.web.dto;

import com.travel.intelligence.api.platform.domain.TravelQueryRecord;
import java.time.Instant;

public record QueryRecordSummary(
        Long id,
        Long conversationId,
        String query,
        String answerPreview,
        Double confidence,
        boolean favorite,
        Instant createdAt
) {
    public static QueryRecordSummary from(TravelQueryRecord record) {
        return new QueryRecordSummary(
                record.getId(),
                record.getConversationId(),
                record.getQueryText(),
                record.getAnswerPreview(),
                record.getConfidence(),
                record.isFavorite(),
                record.getCreatedAt());
    }
}
