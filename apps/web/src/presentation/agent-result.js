const DEGRADATION_BADGES = {
  none: "Hybrid healthy",
  lexical_only: "Lexical fallback",
  dense_only: "Dense fallback",
  no_results: "No indexed evidence",
  all_failed: "Retrieval unavailable",
};

export function buildAgentResultView(response = {}) {
  const retrieval = (response.retrieval_reports || []).map(projectRetrieval);
  const citationReport = response.citation_report || null;
  return {
    answer: response.answer || "无回答文本",
    confidenceLabel: `${Math.round(Number(response.confidence || 0) * 100)}%`,
    evidence: (response.evidence_summary || []).map(projectEvidence),
    retrieval,
    degraded: retrieval.some((item) => item.degradation !== "none"),
    citations: (citationReport?.decisions || []).map((decision) => ({
      claimId: decision.claim_id || "unknown",
      status: decision.status || "unknown",
      reason: decision.reason || "",
      evidenceIds: [...(decision.evidence_ids || [])],
    })),
    citationSummary: citationSummary(response, citationReport),
    timeline: projectTimeline(response),
    limitations: [...(response.limitations || [])],
    metrics: { ...(response.metrics || {}) },
  };
}

function projectEvidence(item = {}) {
  const sourceUrl = item.source_url || "";
  return {
    evidenceId: item.evidence_id || item.chunk_id || "unknown",
    factType: item.fact_type || "fact",
    content: item.content || item.summary || "未提供证据摘要",
    sourceLabel: item.source_title || item.source_name || hostname(sourceUrl) || "未知来源",
    sourceUrl,
    versionLabel: [
      item.document_version_id || item.version_id,
      item.corpus_version || item.version_status,
    ].filter(Boolean).join(" · ") || "版本未知",
  };
}

function projectRetrieval(report = {}) {
  return {
    subtaskId: report.subtask_id || "unknown",
    degradation: report.degradation || "none",
    badge: DEGRADATION_BADGES[report.degradation || "none"] || report.degradation,
    corpusVersion: report.corpus_version || "unknown",
    channels: [report.lexical_attempt, report.dense_attempt]
      .filter(Boolean)
      .map(channelLabel),
  };
}

function channelLabel(attempt) {
  const count = attempt.status === "success" ? ` (${attempt.result_count || 0})` : "";
  const failure = attempt.failure_code ? ` · ${attempt.failure_code}` : "";
  return `${attempt.channel}: ${attempt.status}${count}${failure}`;
}

function projectTimeline(response) {
  const audit = response.orchestration_summary?.state_audit || [];
  const completed = audit.filter((event) =>
    ["phase_succeeded", "phase_recovered", "phase_failed"].includes(event.event_type),
  );
  if (completed.length) {
    return completed.map((event) => ({
      state: event.state || "unknown",
      status: event.status || event.event_type.replace("phase_", ""),
      attempt: Number(event.attempt || 1),
      latency: event.duration_ms == null ? "-" : `${Number(event.duration_ms)} ms`,
      recovery: event.recovery?.strategy || null,
      failureCode: event.failure?.code || null,
    }));
  }
  return (response.visible_trace || []).map((state) => ({
    state: String(state),
    status: "trace",
    attempt: 1,
    latency: "-",
    recovery: null,
    failureCode: null,
  }));
}

function citationSummary(response, report) {
  if (report) {
    const precision = Math.round(Number(report.citation_precision || 0) * 100);
    return `Citation precision ${precision}% · unsupported ${report.unsupported_hard_fact_count || 0}`;
  }
  return response.citation_check_result?.passed ? "Citation check passed" : "No claim-level citation report";
}

function hostname(value) {
  if (!value) return "";
  try {
    return new URL(value).hostname;
  } catch {
    return value;
  }
}
