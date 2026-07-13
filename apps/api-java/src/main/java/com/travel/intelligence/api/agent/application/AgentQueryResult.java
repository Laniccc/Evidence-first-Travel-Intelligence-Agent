package com.travel.intelligence.api.agent.application;

import java.util.LinkedHashMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public record AgentQueryResult(
        String answer,
        String sessionId,
        String queryId,
        Double confidence,
        List<Object> visibleTrace,
        List<Object> evidenceSummary,
        List<Object> limitations,
        List<Object> toolTraces,
        Map<String, Object> structuredResult,
        List<Object> fieldEvidenceSummary,
        List<Object> conflicts,
        Map<String, Object> citationCheckResult,
        Map<String, Object> semanticFrameSummary,
        String answerMode,
        Map<String, Object> rawResponse
) {
    public AgentQueryResult {
        visibleTrace = visibleTrace != null ? new ArrayList<>(visibleTrace) : List.of();
        evidenceSummary = evidenceSummary != null ? new ArrayList<>(evidenceSummary) : List.of();
        limitations = limitations != null ? new ArrayList<>(limitations) : List.of();
        toolTraces = toolTraces != null ? new ArrayList<>(toolTraces) : List.of();
        structuredResult = structuredResult != null ? new LinkedHashMap<>(structuredResult) : Map.of();
        fieldEvidenceSummary = fieldEvidenceSummary != null ? new ArrayList<>(fieldEvidenceSummary) : List.of();
        conflicts = conflicts != null ? new ArrayList<>(conflicts) : List.of();
        citationCheckResult = citationCheckResult != null ? new LinkedHashMap<>(citationCheckResult) : Map.of();
        semanticFrameSummary = semanticFrameSummary != null ? new LinkedHashMap<>(semanticFrameSummary) : Map.of();
        rawResponse = rawResponse != null ? new LinkedHashMap<>(rawResponse) : Map.of();
    }

    public static AgentQueryResult fromRawResponse(Map<String, Object> rawResponse) {
        Map<String, Object> raw = rawResponse != null ? new LinkedHashMap<>(rawResponse) : new LinkedHashMap<>();
        return new AgentQueryResult(
                text(raw, "answer"),
                text(raw, "session_id"),
                text(raw, "query_id"),
                number(raw, "confidence"),
                list(raw, "visible_trace"),
                list(raw, "evidence_summary"),
                list(raw, "limitations"),
                list(raw, "tool_traces"),
                map(raw, "structured_result"),
                list(raw, "field_evidence_summary"),
                list(raw, "conflicts"),
                map(raw, "citation_check_result"),
                map(raw, "semantic_frame_summary"),
                text(raw, "answer_mode"),
                raw);
    }

    public AgentQueryResult withSessionId(String sessionId) {
        Map<String, Object> raw = new LinkedHashMap<>(rawResponse);
        raw.put("session_id", sessionId);
        return new AgentQueryResult(
                answer,
                sessionId,
                queryId,
                confidence,
                visibleTrace,
                evidenceSummary,
                limitations,
                toolTraces,
                structuredResult,
                fieldEvidenceSummary,
                conflicts,
                citationCheckResult,
                semanticFrameSummary,
                answerMode,
                raw);
    }

    private static String text(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        return value instanceof String text && !text.isBlank() ? text : null;
    }

    private static Double number(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        return value instanceof Number number ? number.doubleValue() : null;
    }

    private static List<Object> list(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        return value instanceof List<?> values ? new ArrayList<>(values) : List.of();
    }

    private static Map<String, Object> map(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        if (!(value instanceof Map<?, ?> values)) {
            return Map.of();
        }
        Map<String, Object> copied = new LinkedHashMap<>();
        values.forEach((key, nestedValue) -> copied.put(String.valueOf(key), nestedValue));
        return copied;
    }
}
