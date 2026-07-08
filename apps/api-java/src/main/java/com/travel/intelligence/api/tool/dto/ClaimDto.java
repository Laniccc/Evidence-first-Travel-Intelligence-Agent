package com.travel.intelligence.api.tool.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record ClaimDto(
        @JsonProperty("claim_type") String claimType,
        Object value,
        @JsonProperty("raw_text") String rawText,
        Double confidence) {
}
