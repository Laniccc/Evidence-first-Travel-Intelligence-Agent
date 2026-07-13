const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const QUERY_TIMEOUT_MS = Number(import.meta.env.VITE_QUERY_TIMEOUT_MS || 300000);
const TOKEN_KEY = "travel_platform_token";

export class ApiError extends Error {
  constructor(message, meta = {}) {
    super(message);
    this.name = "ApiError";
    this.status = meta.status;
    this.code = meta.code || "api_error";
  }
}

export function getApiBaseUrl() {
  return API_BASE;
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function clearToken() {
  setToken(null);
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), options.timeoutMs || QUERY_TIMEOUT_MS);
  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new ApiError(data.message || data.error || resp.statusText, {
        status: resp.status,
        code: data.code || data.error,
      });
    }
    return data;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("请求超时，请稍后重试", { code: "timeout" });
    }
    if (err instanceof TypeError) {
      throw new ApiError("无法连接 Java API，请确认后端已启动", { code: "network" });
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}

export function register(payload) {
  return request("/api/auth/register", { method: "POST", body: payload, timeoutMs: 20000 });
}

export function login(payload) {
  return request("/api/auth/login", { method: "POST", body: payload, timeoutMs: 20000 });
}

export function me() {
  return request("/api/auth/me", { method: "GET", timeoutMs: 20000 });
}

export function listConversations() {
  return request("/api/platform/conversations", { method: "GET", timeoutMs: 20000 });
}

export function createConversation(title = "新的旅行咨询") {
  return request("/api/platform/conversations", {
    method: "POST",
    body: { title },
    timeoutMs: 20000,
  });
}

export function getConversation(conversationId) {
  return request(`/api/platform/conversations/${conversationId}`, { method: "GET", timeoutMs: 20000 });
}

export function archiveConversation(conversationId) {
  return request(`/api/platform/conversations/${conversationId}`, { method: "DELETE", timeoutMs: 20000 });
}

export function askTravelAgent(conversationId, payload) {
  return request(`/api/platform/conversations/${conversationId}/query`, {
    method: "POST",
    body: payload,
  });
}

export function getRecordResponse(recordId) {
  return request(`/api/platform/records/${recordId}/response`, { method: "GET" });
}

export function setFavorite(recordId, favorite) {
  return request(`/api/platform/records/${recordId}/favorite`, {
    method: "PUT",
    body: { favorite },
    timeoutMs: 20000,
  });
}

export function listFavorites() {
  return request("/api/platform/favorites", { method: "GET", timeoutMs: 20000 });
}

export function describeError(err) {
  if (err instanceof ApiError) {
    if (err.status === 401) return "登录已过期，请重新登录";
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
