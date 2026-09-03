/**
 * Contract-aligned types (see contracts/schemas/travel_query_*.schema.json).
 */

/**
 * @typedef {Object} TravelQueryRequest
 * @property {string} query
 * @property {string} [session_id]
 * @property {Record<string, unknown>} [user_context]
 * @property {boolean} [debug]
 */

/**
 * @typedef {Object} TravelQueryResponse
 * @property {string} answer
 * @property {string | null} [session_id]
 * @property {string | null} [query_id]
 * @property {string[]} [visible_trace]
 * @property {unknown[]} [evidence_summary]
 * @property {string[]} [limitations]
 * @property {number} [confidence]
 * @property {unknown[]} [tool_traces]
 * @property {Record<string, unknown>} [structured_result]
 * @property {unknown[]} [field_evidence_summary]
 * @property {unknown[]} [conflicts]
 * @property {Record<string, unknown> | null} [citation_check_result]
 * @property {Record<string, unknown> | null} [semantic_frame_summary]
 * @property {string | null} [answer_mode]
 * @property {AnswerClaim[]} [answer_claims]
 * @property {CitationReport | null} [citation_report]
 * @property {RetrievalReport[]} [retrieval_reports]
 * @property {Record<string, number>} [metrics]
 * @property {{run_id?: string, terminal_state?: string, state_audit?: StateAuditEvent[]}} [orchestration_summary]
 */

/** @typedef {{claim_id: string, text: string, claim_type: string, hard_fact: boolean, evidence_ids: string[]}} AnswerClaim */
/** @typedef {{passed: boolean, safe_failure: boolean, citation_precision: number, unsupported_hard_fact_count: number, decisions: Array<{claim_id: string, status: string, reason: string, evidence_ids: string[]}>}} CitationReport */
/** @typedef {{subtask_id: string, corpus_version: string, degradation: string, lexical_attempt: RetrievalAttempt, dense_attempt: RetrievalAttempt, final_hits: unknown[]}} RetrievalReport */
/** @typedef {{channel: string, status: string, result_count: number, latency_ms: number, failure_code?: string | null}} RetrievalAttempt */
/** @typedef {{event_type: string, state: string, status: string, attempt: number, duration_ms?: number, recovery?: {strategy?: string}, failure?: {code?: string}}} StateAuditEvent */

export {};
