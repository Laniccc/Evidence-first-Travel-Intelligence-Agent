package com.travel.intelligence.api.platform.web.dto;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AskTravelAgentRequest(
        @NotBlank @Size(max = 1000) String query,
        JsonNode userContext,
        Boolean debug
) {
}
