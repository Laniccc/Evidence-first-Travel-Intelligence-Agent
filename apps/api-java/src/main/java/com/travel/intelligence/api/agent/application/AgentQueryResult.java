package com.travel.intelligence.api.agent.application;

import java.util.ArrayList;
import java.util.LinkedHashMap;
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
        List<Map<String, Object>> answerClaims,
        CitationReport citationReport,
        List<RetrievalReport> retrievalReports,
        Map<String, Double> metrics,
        Map<String, Object> orchestrationSummary,
        PromotionSummary promotionSummary,
        IndexSyncStatus indexSyncStatus,
        Map<String, Object> rawResponse
) {
    public AgentQueryResult {
        visibleTrace = copyList(visibleTrace);
        evidenceSummary = copyList(evidenceSummary);
        limitations = copyList(limitations);
        toolTraces = copyList(toolTraces);
        structuredResult = copyMap(structuredResult);
        fieldEvidenceSummary = copyList(fieldEvidenceSummary);
        conflicts = copyList(conflicts);
        citationCheckResult = copyMap(citationCheckResult);
        semanticFrameSummary = copyMap(semanticFrameSummary);
        answerClaims = answerClaims != null ? new ArrayList<>(answerClaims) : List.of();
        retrievalReports = retrievalReports != null ? new ArrayList<>(retrievalReports) : List.of();
        metrics = metrics != null ? new LinkedHashMap<>(metrics) : Map.of();
        orchestrationSummary = copyMap(orchestrationSummary);
        rawResponse = copyMap(rawResponse);
    }

    public static AgentQueryResult fromRawResponse(Map<String, Object> rawResponse) {
        Map<String, Object> raw = copyMap(rawResponse);
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
                mapList(raw, "answer_claims"),
                CitationReport.from(mapOrNull(raw, "citation_report")),
                mapList(raw, "retrieval_reports").stream().map(RetrievalReport::from).toList(),
                numberMap(raw, "metrics"),
                map(raw, "orchestration_summary"),
                PromotionSummary.from(mapOrNull(raw, "promotion_summary")),
                IndexSyncStatus.from(mapOrNull(raw, "index_sync_status")),
                raw);
    }

    public AgentQueryResult withSessionId(String sessionId) {
        Map<String, Object> raw = new LinkedHashMap<>(rawResponse);
        raw.put("session_id", sessionId);
        return new AgentQueryResult(
                answer, sessionId, queryId, confidence, visibleTrace, evidenceSummary,
                limitations, toolTraces, structuredResult, fieldEvidenceSummary, conflicts,
                citationCheckResult, semanticFrameSummary, answerMode, answerClaims,
                citationReport, retrievalReports, metrics, orchestrationSummary, promotionSummary, indexSyncStatus, raw);
    }

    public record PromotionSummary(String status, int candidateCount, int publishedCount, int pendingCount, int rejectedCount) {
        static PromotionSummary from(Map<String, Object> value) {
            return value == null ? null : new PromotionSummary(text(value, "status"), integer(value, "candidate_count"),
                    integer(value, "published_count"), integer(value, "pending_count"), integer(value, "rejected_count"));
        }
    }

    public record IndexSyncStatus(String status, int pendingCount, int indexedCount, int failedCount) {
        static IndexSyncStatus from(Map<String, Object> value) {
            return value == null ? null : new IndexSyncStatus(text(value, "status"), integer(value, "pending_count"),
                    integer(value, "indexed_count"), integer(value, "failed_count"));
        }
    }

    public record RetrievalReport(
            String subtaskId,
            String corpusVersion,
            String degradation,
            Map<String, Object> lexicalAttempt,
            Map<String, Object> denseAttempt,
            List<Map<String, Object>> finalHits,
            Map<String, Object> raw
    ) {
        static RetrievalReport from(Map<String, Object> value) {
            return new RetrievalReport(
                    text(value, "subtask_id"),
                    text(value, "corpus_version"),
                    text(value, "degradation"),
                    map(value, "lexical_attempt"),
                    map(value, "dense_attempt"),
                    mapList(value, "final_hits"),
                    copyMap(value));
        }
    }

    public record CitationReport(
            boolean passed,
            boolean safeFailure,
            int unsupportedHardFactCount,
            double citationPrecision,
            List<CitationDecision> decisions
    ) {
        static CitationReport from(Map<String, Object> value) {
            if (value == null) {
                return null;
            }
            List<CitationDecision> decisions = mapList(value, "decisions").stream()
                    .map(CitationDecision::from)
                    .toList();
            return new CitationReport(
                    bool(value, "passed"),
                    bool(value, "safe_failure"),
                    integer(value, "unsupported_hard_fact_count"),
                    numberOrZero(value, "citation_precision"),
                    decisions);
        }
    }

    public record CitationDecision(String claimId, String status, String reason, List<String> evidenceIds) {
        static CitationDecision from(Map<String, Object> value) {
            return new CitationDecision(
                    text(value, "claim_id"),
                    text(value, "status"),
                    text(value, "reason"),
                    stringList(value, "evidence_ids"));
        }
    }

    private static List<Object> copyList(List<Object> value) {
        return value != null ? new ArrayList<>(value) : List.of();
    }

    private static Map<String, Object> copyMap(Map<String, Object> value) {
        return value != null ? new LinkedHashMap<>(value) : new LinkedHashMap<>();
    }

    private static String text(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        return value instanceof String text && !text.isBlank() ? text : null;
    }

    private static Double number(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        return value instanceof Number number ? number.doubleValue() : null;
    }

    private static double numberOrZero(Map<String, Object> raw, String field) {
        Double value = number(raw, field);
        return value != null ? value : 0.0;
    }

    private static int integer(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        return value instanceof Number number ? number.intValue() : 0;
    }

    private static boolean bool(Map<String, Object> raw, String field) {
        return raw.get(field) instanceof Boolean value && value;
    }

    private static List<Object> list(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        return value instanceof List<?> values ? new ArrayList<>(values) : List.of();
    }

    private static Map<String, Object> map(Map<String, Object> raw, String field) {
        Map<String, Object> value = mapOrNull(raw, field);
        return value != null ? value : Map.of();
    }

    private static Map<String, Object> mapOrNull(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        if (!(value instanceof Map<?, ?> values)) {
            return null;
        }
        Map<String, Object> copied = new LinkedHashMap<>();
        values.forEach((key, nestedValue) -> copied.put(String.valueOf(key), nestedValue));
        return copied;
    }

    private static List<Map<String, Object>> mapList(Map<String, Object> raw, String field) {
        Object value = raw.get(field);
        if (!(value instanceof List<?> values)) {
            return List.of();
        }
        List<Map<String, Object>> copied = new ArrayList<>();
        for (Object item : values) {
            if (item instanceof Map<?, ?> map) {
                Map<String, Object> row = new LinkedHashMap<>();
                map.forEach((key, nestedValue) -> row.put(String.valueOf(key), nestedValue));
                copied.add(row);
            }
        }
        return copied;
    }

    private static Map<String, Double> numberMap(Map<String, Object> raw, String field) {
        Map<String, Object> values = map(raw, field);
        Map<String, Double> copied = new LinkedHashMap<>();
        values.forEach((key, value) -> {
            if (value instanceof Number number) {
                copied.put(key, number.doubleValue());
            }
        });
        return copied;
    }

    private static List<String> stringList(Map<String, Object> raw, String field) {
        return list(raw, field).stream()
                .filter(String.class::isInstance)
                .map(String.class::cast)
                .toList();
    }
}
