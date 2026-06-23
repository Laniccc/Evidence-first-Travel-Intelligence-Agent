/**
 * Travel API client — calls Java Gateway only (never /agent/query).
 * @typedef {import('./types.js').TravelQueryRequest} TravelQueryRequest
 * @typedef {import('./types.js').TravelQueryResponse} TravelQueryResponse
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const QUERY_TIMEOUT_MS = Number(import.meta.env.VITE_QUERY_TIMEOUT_MS || 300000);

export class TravelQueryError extends Error {
  /**
   * @param {string} message
   * @param {{ kind?: string, status?: number, detail?: string }} [meta]
   */
  constructor(message, meta = {}) {
    super(message);
    this.name = "TravelQueryError";
    this.kind = meta.kind || "unknown";
    this.status = meta.status;
    this.detail = meta.detail;
  }
}

/**
 * @returns {string}
 */
export function getApiBaseUrl() {
  return API_BASE;
}

/**
 * @returns {number}
 */
export function getQueryTimeoutMs() {
  return QUERY_TIMEOUT_MS;
}

/**
 * @param {unknown} err
 * @returns {string}
 */
export function describeTravelQueryError(err) {
  if (err instanceof TravelQueryError) {
    if (err.kind === "timeout") {
      return (
        "查询超时：证据检索与答案合成耗时较长（通常 1–3 分钟，复杂问题可能更久）。" +
        "请稍后重试；若反复超时，请确认 api-java (:8082) 与 agent-python (:8001) 仍在运行。"
      );
    }
    if (err.kind === "gateway_timeout") {
      return (
        "Gateway 等待 Agent 超时。请确认 agent-python (:8001) 正常，" +
        "并将 api-java 的 agent.read-timeout 设为至少 300s 后重启 Gateway。"
      );
    }
    if (err.kind === "network") {
      return (
        "无法连接 API Gateway。请确认 api-java 已启动（默认 :8082）" +
        "，且 Vite 代理或 VITE_API_BASE_URL 配置正确。"
      );
    }
    if (err.kind === "gateway") {
      return `Gateway 错误：${err.detail || err.message}`;
    }
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}

/**
 * @param {unknown} err
 * @returns {string[]}
 */
export function buildErrorTrace(err) {
  const lines = ["请求未完成，未收到完整回答。"];
  if (err instanceof TravelQueryError) {
    if (err.kind === "timeout" || err.kind === "gateway_timeout") {
      lines.push("原因：等待后端响应超时（检索类问题耗时较长）。");
      lines.push("建议：保持 agent-python (:8001) 与 api-java (:8082) 运行后重试同一问题。");
    } else if (err.kind === "network") {
      lines.push("原因：浏览器无法连接到 API Gateway。");
      lines.push("建议：启动 api-java（:8082）与 agent-python (:8001）。");
    } else if (err.detail) {
      lines.push(`详情：${err.detail}`);
    }
    return lines;
  }
  lines.push(`详情：${err instanceof Error ? err.message : String(err)}`);
  return lines;
}

/**
 * @param {Response} resp
 * @param {Record<string, unknown>} data
 * @returns {TravelQueryError}
 */
function httpTravelQueryError(resp, data) {
  const detail = String(data.message || data.error || resp.statusText || "unknown");
  if (resp.status === 504 || detail.includes("agent_timeout")) {
    return new TravelQueryError(detail, {
      kind: "gateway_timeout",
      status: resp.status,
      detail,
    });
  }
  if (resp.status === 502 || resp.status === 503 || detail.includes("agent_unavailable")) {
    return new TravelQueryError(detail, {
      kind: "gateway",
      status: resp.status,
      detail,
    });
  }
  return new TravelQueryError(`请求失败 (${resp.status}): ${detail}`, {
    kind: "http",
    status: resp.status,
    detail,
  });
}

/**
 * @param {TravelQueryRequest} payload
 * @returns {Promise<TravelQueryResponse>}
 */
export async function postTravelQuery(payload) {
  const url = API_BASE ? `${API_BASE}/api/travel/query` : "/api/travel/query";
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), QUERY_TIMEOUT_MS);

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    const data = await resp.json().catch(() => (/** @type {Record<string, unknown>} */ ({})));
    if (!resp.ok) {
      throw httpTravelQueryError(resp, data);
    }
    return /** @type {TravelQueryResponse} */ (data);
  } catch (err) {
    if (err instanceof TravelQueryError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new TravelQueryError("client_timeout", { kind: "timeout" });
    }
    if (err instanceof TypeError) {
      throw new TravelQueryError("network_error", { kind: "network" });
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
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
