package com.travel.intelligence.api.platform.web.dto;

import java.util.Map;

public record AskTravelAgentResponse(
        QueryRecordSummary record,
        Map<String, Object> agentResponse
) {
}
