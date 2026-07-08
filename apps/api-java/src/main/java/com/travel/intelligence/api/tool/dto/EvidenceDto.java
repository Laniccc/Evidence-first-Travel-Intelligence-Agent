package com.travel.intelligence.api.tool.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.UUID;

public record EvidenceDto(
        @JsonProperty("evidence_id") String evidenceId,
        @JsonProperty("source_name") String sourceName,
        @JsonProperty("source_type") String sourceType,
        List<ClaimDto> claims,
        double confidence,
        List<String> limitations,
        @JsonProperty("source_url") String sourceUrl,
        String country,
        String city,
        @JsonProperty("place_name") String placeName) {

    public EvidenceDto {
        if (evidenceId == null || evidenceId.isBlank()) {
            evidenceId = UUID.randomUUID().toString();
        }
        if (claims == null) {
            claims = List.of();
        }
        if (limitations == null) {
            limitations = List.of();
        }
    }

    public static EvidenceDto of(
            String sourceName,
            String sourceType,
            List<ClaimDto> claims,
            double confidence,
            List<String> limitations) {
        return new EvidenceDto(null, sourceName, sourceType, claims, confidence, limitations, null, null, null, null);
    }
}
