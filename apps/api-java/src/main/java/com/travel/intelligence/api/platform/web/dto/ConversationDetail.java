package com.travel.intelligence.api.platform.web.dto;

import java.util.List;

public record ConversationDetail(
        ConversationSummary conversation,
        List<QueryRecordSummary> records
) {
}
