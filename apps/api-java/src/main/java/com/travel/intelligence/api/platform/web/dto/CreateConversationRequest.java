package com.travel.intelligence.api.platform.web.dto;

import jakarta.validation.constraints.Size;

public record CreateConversationRequest(
        @Size(max = 120) String title
) {
}
