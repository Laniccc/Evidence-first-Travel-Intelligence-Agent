package com.travel.intelligence.api.tool.mcp;

import com.travel.intelligence.api.tool.dto.ClaimDto;
import com.travel.intelligence.api.tool.dto.EvidenceDto;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class SearchMcpEvidenceMapper {

    private static final Map<String, String> NEED_TO_CLAIM = Map.of(
            "opening_hours", "opening_hours",
            "ticket_price", "ticket_price",
            "weather", "weather",
            "today_weather", "weather",
            "seasonality", "seasonality",
            "best_time_to_visit", "best_time_to_visit",
            "current_crowd", "crowd",
            "crowd_level", "crowd");

    public List<EvidenceDto> toEvidence(Object raw, Map<String, Object> arguments) {
        if (raw == null) {
            return List.of();
        }
        if (raw instanceof List<?> list) {
            List<EvidenceDto> out = new ArrayList<>();
            for (Object item : list) {
                out.addAll(toEvidence(item, arguments));
            }
            return out;
        }
        if (raw instanceof Map<?, ?> map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> payload = (Map<String, Object>) map;
            if (payload.containsKey("evidence")) {
                return toEvidence(payload.get("evidence"), arguments);
            }
            if (payload.containsKey("source_name") && payload.containsKey("claims")) {
                return List.of(fromStructuredPayload(payload, arguments));
            }
            if (payload.containsKey("results")) {
                return List.of(fromSearchResults(payload, arguments));
            }
            return List.of(fromGenericPayload(payload, arguments));
        }
        return List.of(fromTextExcerpt(String.valueOf(raw), arguments, null));
    }

    private EvidenceDto fromStructuredPayload(Map<String, Object> payload, Map<String, Object> arguments) {
        List<ClaimDto> claims = parseClaims(payload.get("claims"));
        if (claims.isEmpty()) {
            claims = List.of(textClaim(excerptText(payload), claimTypeFor(arguments), 0.65));
        }
        return new EvidenceDto(
                stringOrNull(payload.get("evidence_id")),
                stringOrDefault(payload.get("source_name"), "search_mcp"),
                stringOrDefault(payload.get("source_type"), "web"),
                claims,
                doubleOrDefault(payload.get("confidence"), 0.7),
                mergeLimitations(payload, arguments),
                stringOrNull(payload.get("source_url")),
                stringOrNull(payload.get("country")),
                stringOrNull(payload.get("city")),
                stringOrNull(payload.get("place_name")));
    }

    private EvidenceDto fromSearchResults(Map<String, Object> payload, Map<String, Object> arguments) {
        Object resultsObj = payload.get("results");
        List<String> snippets = new ArrayList<>();
        String sourceUrl = null;
        if (resultsObj instanceof List<?> results) {
            for (Object item : results) {
                if (!(item instanceof Map<?, ?> row)) {
                    continue;
                }
                @SuppressWarnings("unchecked")
                Map<String, Object> rowMap = (Map<String, Object>) row;
                String snippet = firstNonBlank(
                        stringOrNull(rowMap.get("snippet")),
                        stringOrNull(rowMap.get("summary")),
                        stringOrNull(rowMap.get("title")));
                if (snippet != null) {
                    snippets.add(snippet);
                }
                if (sourceUrl == null) {
                    sourceUrl = stringOrNull(rowMap.get("url"));
                }
            }
        }
        String excerpt = snippets.isEmpty() ? excerptText(payload) : String.join(" | ", snippets);
        ClaimDto claim = textClaim(excerpt, claimTypeFor(arguments), 0.68);
        return new EvidenceDto(
                null,
                "search_mcp",
                "web",
                List.of(claim),
                0.68,
                mergeLimitations(payload, arguments),
                sourceUrl,
                placeField(arguments, "country"),
                placeField(arguments, "city"),
                placeField(arguments, "place_name"));
    }

    private EvidenceDto fromGenericPayload(Map<String, Object> payload, Map<String, Object> arguments) {
        List<ClaimDto> claims = parseClaims(payload.get("claims"));
        if (claims.isEmpty()) {
            String excerpt = excerptText(payload);
            claims = List.of(textClaim(excerpt, claimTypeFor(arguments), 0.65));
        }
        return new EvidenceDto(
                null,
                stringOrDefault(payload.get("source_name"), "search_mcp"),
                stringOrDefault(payload.get("source_type"), "web"),
                claims,
                doubleOrDefault(payload.get("confidence"), 0.65),
                mergeLimitations(payload, arguments),
                firstNonBlank(stringOrNull(payload.get("source_url")), stringOrNull(payload.get("url"))),
                stringOrNull(payload.get("country")),
                stringOrNull(payload.get("city")),
                stringOrNull(payload.get("place_name")));
    }

    private EvidenceDto fromTextExcerpt(String text, Map<String, Object> arguments, String sourceUrl) {
        ClaimDto claim = textClaim(text, claimTypeFor(arguments), 0.6);
        return new EvidenceDto(
                null,
                "search_mcp",
                "web",
                List.of(claim),
                0.6,
                mergeLimitations(Map.of(), arguments),
                sourceUrl,
                placeField(arguments, "country"),
                placeField(arguments, "city"),
                placeField(arguments, "place_name"));
    }

    private List<ClaimDto> parseClaims(Object rawClaims) {
        if (!(rawClaims instanceof List<?> list)) {
            return List.of();
        }
        List<ClaimDto> claims = new ArrayList<>();
        for (Object item : list) {
            if (!(item instanceof Map<?, ?> map)) {
                continue;
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> claimMap = (Map<String, Object>) map;
            String claimType = stringOrDefault(claimMap.get("claim_type"), "travel_advice");
            Object value = claimMap.containsKey("value") ? claimMap.get("value") : claimMap.get("text");
            String rawText = stringOrNull(claimMap.get("raw_text"));
            Double confidence = claimMap.get("confidence") instanceof Number n ? n.doubleValue() : null;
            if (value != null) {
                claims.add(new ClaimDto(claimType, value, rawText != null ? rawText : String.valueOf(value), confidence));
            }
        }
        return claims;
    }

    private ClaimDto textClaim(String text, String claimType, double confidence) {
        return new ClaimDto(claimType, text, text, confidence);
    }

    private String excerptText(Map<String, Object> payload) {
        return firstNonBlank(
                stringOrNull(payload.get("text")),
                stringOrNull(payload.get("content")),
                stringOrNull(payload.get("summary")),
                stringOrNull(payload.get("preview")));
    }

    private String claimTypeFor(Map<String, Object> arguments) {
        if (arguments == null) {
            return "travel_advice";
        }
        for (String key : List.of("information_need", "need_type", "query_type")) {
            Object value = arguments.get(key);
            if (value instanceof String need && NEED_TO_CLAIM.containsKey(need)) {
                return NEED_TO_CLAIM.get(need);
            }
        }
        return "travel_advice";
    }

    private List<String> mergeLimitations(Map<String, Object> payload, Map<String, Object> arguments) {
        Set<String> limitations = new LinkedHashSet<>();
        Object fromPayload = payload.get("limitations");
        if (fromPayload instanceof List<?> list) {
            for (Object item : list) {
                if (item != null) {
                    limitations.add(String.valueOf(item));
                }
            }
        }
        limitations.add("mcp_server=search");
        limitations.add("mcp_tool=public_web_search");
        limitations.add("evidence_excerpt_only=true");
        return List.copyOf(limitations);
    }

    private static String stringOrNull(Object value) {
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value).trim();
        return text.isEmpty() ? null : text;
    }

    private static String stringOrDefault(Object value, String fallback) {
        String text = stringOrNull(value);
        return text != null ? text : fallback;
    }

    private static double doubleOrDefault(Object value, double fallback) {
        return value instanceof Number n ? n.doubleValue() : fallback;
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return "";
    }

    private static String placeField(Map<String, Object> arguments, String key) {
        if (arguments == null) {
            return null;
        }
        return stringOrNull(arguments.get(key));
    }
}
