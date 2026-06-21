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
 */

export {};
