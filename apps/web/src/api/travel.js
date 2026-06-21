/**
 * Travel API client — calls Java Gateway only (never /agent/query).
 * @typedef {import('./types.js').TravelQueryRequest} TravelQueryRequest
 * @typedef {import('./types.js').TravelQueryResponse} TravelQueryResponse
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

/**
 * @returns {string}
 */
export function getApiBaseUrl() {
  return API_BASE;
}

/**
 * @param {TravelQueryRequest} payload
 * @returns {Promise<TravelQueryResponse>}
 */
export async function postTravelQuery(payload) {
  const url = `${API_BASE}/api/travel/query`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = data.message || data.error || resp.statusText;
    throw new Error(`请求失败 (${resp.status}): ${detail}`);
  }
  return /** @type {TravelQueryResponse} */ (data);
}

/**
 * @param {string} query
 * @param {Record<string, unknown>} userContext
 * @param {string | null} [sessionId]
 * @returns {TravelQueryRequest}
 */
export function buildTravelQueryRequest(query, userContext, sessionId = null) {
  /** @type {TravelQueryRequest} */
  const payload = {
    query,
    user_context: userContext,
    debug: false,
  };
  if (sessionId) {
    payload.session_id = sessionId;
  }
  return payload;
}
