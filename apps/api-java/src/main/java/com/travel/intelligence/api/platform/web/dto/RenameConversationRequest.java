package com.travel.intelligence.api.platform.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RenameConversationRequest(
        @NotBlank @Size(max = 120) String title
) {
}
