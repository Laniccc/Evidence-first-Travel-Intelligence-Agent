import "./styles.css";
import { buildAgentResultView } from "./presentation/agent-result.js";
import {
  archiveConversation,
  askTravelAgent,
  clearToken,
  createConversation,
  describeError,
  getApiBaseUrl,
  getConversation,
  getRecordResponse,
  getToken,
  listConversations,
  listFavorites,
  login,
  me,
  register,
  setFavorite,
  setToken,
} from "./api/travel.js";

const state = {
  user: null,
  conversations: [],
  currentConversation: null,
  records: [],
  favorites: [],
  currentRecord: null,
  currentResponse: null,
  loading: false,
};

const els = {
  authView: document.getElementById("auth-view"),
  appView: document.getElementById("app-view"),
  authForm: document.getElementById("auth-form"),
  authTitle: document.getElementById("auth-title"),
  authToggle: document.getElementById("auth-toggle"),
  authSubmit: document.getElementById("auth-submit"),
  authError: document.getElementById("auth-error"),
  displayNameGroup: document.getElementById("display-name-group"),
  username: document.getElementById("username"),
  email: document.getElementById("email"),
  password: document.getElementById("password"),
  displayName: document.getElementById("display-name"),
  userName: document.getElementById("user-name"),
  logout: document.getElementById("logout"),
  newConversation: document.getElementById("new-conversation"),
  archiveConversation: document.getElementById("archive-conversation"),
  conversationList: document.getElementById("conversation-list"),
  favoriteList: document.getElementById("favorite-list"),
  conversationTitle: document.getElementById("conversation-title"),
  recordList: document.getElementById("record-list"),
  query: document.getElementById("query"),
  submit: document.getElementById("submit"),
  answer: document.getElementById("answer"),
  answerMeta: document.getElementById("answer-meta"),
  favoriteCurrent: document.getElementById("favorite-current"),
  errorBox: document.getElementById("error-box"),
  contextDate: document.getElementById("context-date"),
  contextCity: document.getElementById("context-city"),
  contextParty: document.getElementById("context-party"),
  traceDetail: document.getElementById("trace-detail"),
  evidenceDetail: document.getElementById("evidence-detail"),
};

let authMode = "login";

function show(el, visible) {
  el.classList.toggle("hidden", !visible);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function setError(message) {
  els.errorBox.textContent = message || "";
  show(els.errorBox, Boolean(message));
}

function setAuthError(message) {
  els.authError.textContent = message || "";
  show(els.authError, Boolean(message));
}

function switchAuthMode(mode) {
  authMode = mode;
  const isRegister = mode === "register";
  els.authTitle.textContent = isRegister ? "创建平台账号" : "登录 Travel Agent 平台";
  els.authSubmit.textContent = isRegister ? "注册并进入" : "登录";
  els.authToggle.textContent = isRegister ? "已有账号，去登录" : "没有账号，创建一个";
  show(els.displayNameGroup, isRegister);
  els.email.required = isRegister;
  setAuthError("");
}

async function handleAuth(event) {
  event.preventDefault();
  setAuthError("");
  els.authSubmit.disabled = true;
  try {
    const payload = {
      username: els.username.value.trim(),
      password: els.password.value,
    };
    const data =
      authMode === "register"
        ? await register({
            ...payload,
            email: els.email.value.trim(),
            displayName: els.displayName.value.trim(),
          })
        : await login({ usernameOrEmail: payload.username, password: payload.password });
    setToken(data.token);
    state.user = data.user;
    await enterApp();
  } catch (err) {
    setAuthError(describeError(err));
  } finally {
    els.authSubmit.disabled = false;
  }
}

async function boot() {
  wireEvents();
  const health = document.getElementById("link-health");
  if (health) health.href = `${getApiBaseUrl() || ""}/health`;
  if (!getToken()) {
    showAuth();
    return;
  }
  try {
    state.user = await me();
    await enterApp();
  } catch {
    clearToken();
    showAuth();
  }
}

function showAuth() {
  show(els.authView, true);
  show(els.appView, false);
  switchAuthMode("login");
}

async function enterApp() {
  show(els.authView, false);
  show(els.appView, true);
  els.userName.textContent = state.user?.displayName || state.user?.username || "用户";
  await refreshConversations();
  await refreshFavorites();
}

async function refreshConversations() {
  state.conversations = await listConversations();
  if (!state.conversations.length) {
    const created = await createConversation("我的旅行咨询");
    state.conversations = [created];
  }
  const currentId = state.currentConversation?.id;
  const next = state.conversations.find((item) => item.id === currentId) || state.conversations[0];
  await selectConversation(next.id);
}

async function selectConversation(conversationId) {
  const detail = await getConversation(conversationId);
  state.currentConversation = detail.conversation;
  state.records = detail.records || [];
  state.currentRecord = state.records[state.records.length - 1] || null;
  state.currentResponse = state.currentRecord ? await getRecordResponse(state.currentRecord.id) : null;
  render();
}

async function submitQuery() {
  const query = els.query.value.trim();
  if (!query || !state.currentConversation) return;
  state.loading = true;
  setError("");
  renderComposerState();
  try {
    const data = await askTravelAgent(state.currentConversation.id, {
      query,
      userContext: buildUserContext(),
      debug: false,
    });
    els.query.value = "";
    state.currentRecord = data.record;
    state.currentResponse = data.agentResponse;
    const detail = await getConversation(state.currentConversation.id);
    state.currentConversation = detail.conversation;
    state.records = detail.records || [];
    state.conversations = await listConversations();
    await refreshFavorites();
    render();
  } catch (err) {
    setError(describeError(err));
  } finally {
    state.loading = false;
    renderComposerState();
  }
}

function buildUserContext() {
  const ctx = {};
  const date = els.contextDate.value.trim();
  const city = els.contextCity.value.trim();
  const party = els.contextParty.value;
  if (date) ctx.travel_date = date;
  if (city) ctx.start_location = city;
  if (party) ctx.party = [party];
  return ctx;
}

function render() {
  renderConversations();
  renderRecords();
  renderFavorites();
  renderAnswer();
  renderComposerState();
}

function renderConversations() {
  els.conversationList.innerHTML = state.conversations
    .map(
      (item) => `
        <button class="list-item ${item.id === state.currentConversation?.id ? "active" : ""}" data-conversation-id="${item.id}">
          <span>${escapeHtml(item.title)}</span>
          <small>${new Date(item.updatedAt).toLocaleString()}</small>
        </button>
      `,
    )
    .join("");
  els.conversationTitle.textContent = state.currentConversation?.title || "旅行咨询";
}

function renderRecords() {
  if (!state.records.length) {
    els.recordList.innerHTML = `<div class="empty">暂无提问记录</div>`;
    return;
  }
  els.recordList.innerHTML = state.records
    .map(
      (item) => `
        <button class="record-item ${item.id === state.currentRecord?.id ? "active" : ""}" data-record-id="${item.id}">
          <span>${escapeHtml(item.query)}</span>
          <small>${new Date(item.createdAt).toLocaleString()}${item.favorite ? " · 已收藏" : ""}</small>
        </button>
      `,
    )
    .join("");
}

function renderFavorites() {
  if (!state.favorites.length) {
    els.favoriteList.innerHTML = `<div class="empty">暂无收藏</div>`;
    return;
  }
  els.favoriteList.innerHTML = state.favorites
    .slice(0, 8)
    .map(
      (item) => `
        <button class="favorite-item" data-record-id="${item.id}">
          <span>${escapeHtml(item.query)}</span>
          <small>${new Date(item.createdAt).toLocaleDateString()}</small>
        </button>
      `,
    )
    .join("");
}

function renderAnswer() {
  if (!state.currentResponse) {
    els.answer.textContent = "选择一个会话，向 Travel Agent 提问。";
    els.answerMeta.innerHTML = "";
    els.traceDetail.textContent = "";
    els.evidenceDetail.textContent = "";
    els.favoriteCurrent.disabled = true;
    els.favoriteCurrent.textContent = "收藏回答";
    return;
  }
  const data = state.currentResponse;
  const view = buildAgentResultView(data);
  els.answer.textContent = view.answer;
  els.answerMeta.innerHTML = `
    <span class="badge">置信度 ${view.confidenceLabel}</span>
    <span class="badge">证据 ${view.evidence.length}</span>
    <span class="badge ${view.degraded ? "badge-warn" : "badge-ok"}">${
      view.retrieval[0]?.badge || "Legacy response"
    }</span>
  `;
  els.traceDetail.innerHTML = renderTimeline(view.timeline);
  els.evidenceDetail.innerHTML = renderEvidenceAudit(view);
  els.favoriteCurrent.disabled = !state.currentRecord;
  els.favoriteCurrent.textContent = state.currentRecord?.favorite ? "取消收藏" : "收藏回答";
}

function renderTimeline(timeline) {
  if (!timeline.length) return `<div class="empty">暂无状态审计记录</div>`;
  return `<div class="audit-timeline">${timeline
    .map(
      (item) => `<div class="audit-row">
        <span class="audit-state">${escapeHtml(item.state)}</span>
        <span class="status-${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
        <small>attempt ${item.attempt} · ${escapeHtml(item.latency)}</small>
        ${item.recovery ? `<small>recovery: ${escapeHtml(item.recovery)}</small>` : ""}
        ${item.failureCode ? `<small class="danger-text">${escapeHtml(item.failureCode)}</small>` : ""}
      </div>`,
    )
    .join("")}</div>`;
}

function renderEvidenceAudit(view) {
  const evidence = view.evidence.length
    ? view.evidence
        .map((item) => {
          const href = safeHref(item.sourceUrl);
          const source = href
            ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(item.sourceLabel)}</a>`
            : escapeHtml(item.sourceLabel);
          return `<article class="evidence-card">
            <div><strong>${escapeHtml(item.factType)}</strong><span class="evidence-id">${escapeHtml(item.evidenceId)}</span></div>
            <p>${escapeHtml(item.content)}</p>
            <small>${source} · ${escapeHtml(item.versionLabel)}</small>
          </article>`;
        })
        .join("")
    : `<div class="empty">没有可展示的 Evidence</div>`;
  const retrieval = view.retrieval
    .map(
      (item) => `<article class="retrieval-card">
        <strong>${escapeHtml(item.badge)}</strong>
        <small>${escapeHtml(item.subtaskId)} · ${escapeHtml(item.corpusVersion)}</small>
        <div>${item.channels.map((channel) => `<code>${escapeHtml(channel)}</code>`).join("")}</div>
      </article>`,
    )
    .join("");
  const citations = view.citations
    .map(
      (item) => `<li><strong>${escapeHtml(item.claimId)}</strong> · ${escapeHtml(item.status)}<br><small>${escapeHtml(item.reason)} · ${escapeHtml(item.evidenceIds.join(", "))}</small></li>`,
    )
    .join("");
  const limitations = view.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `<div class="evidence-audit">
    <h4>Evidence</h4>${evidence}
    ${view.knowledge ? `<h4>知识维护</h4><p>${escapeHtml(view.knowledge.label)}</p>
      <small>已发布 ${view.knowledge.published} · 待审核 ${view.knowledge.pendingReview} · 已拒绝 ${view.knowledge.rejected}<br>${escapeHtml(view.knowledge.note)}</small>` : ""}
    ${retrieval ? `<h4>Retrieval</h4>${retrieval}` : ""}
    <h4>Citation</h4><p class="citation-summary">${escapeHtml(view.citationSummary)}</p>
    ${citations ? `<ul>${citations}</ul>` : ""}
    ${limitations ? `<h4>Limitations</h4><ul>${limitations}</ul>` : ""}
  </div>`;
}

function safeHref(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function renderComposerState() {
  els.submit.disabled = state.loading || !state.currentConversation;
  els.submit.textContent = state.loading ? "Agent 思考中" : "发送";
}

async function refreshFavorites() {
  state.favorites = await listFavorites();
}

function wireEvents() {
  els.authForm.addEventListener("submit", handleAuth);
  els.authToggle.addEventListener("click", () => switchAuthMode(authMode === "login" ? "register" : "login"));
  els.logout.addEventListener("click", () => {
    clearToken();
    state.user = null;
    state.currentConversation = null;
    showAuth();
  });
  els.newConversation.addEventListener("click", async () => {
    const created = await createConversation("新的旅行咨询");
    state.conversations = [created, ...state.conversations];
    await selectConversation(created.id);
  });
  els.archiveConversation.addEventListener("click", async () => {
    if (!state.currentConversation) return;
    await archiveConversation(state.currentConversation.id);
    state.currentConversation = null;
    await refreshConversations();
  });
  els.submit.addEventListener("click", submitQuery);
  els.query.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") submitQuery();
  });
  els.favoriteCurrent.addEventListener("click", async () => {
    if (!state.currentRecord) return;
    const updated = await setFavorite(state.currentRecord.id, !state.currentRecord.favorite);
    state.currentRecord = updated;
    state.records = state.records.map((item) => (item.id === updated.id ? updated : item));
    await refreshFavorites();
    render();
  });
  els.conversationList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-conversation-id]");
    if (button) await selectConversation(Number(button.dataset.conversationId));
  });
  els.recordList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-record-id]");
    if (!button) return;
    const recordId = Number(button.dataset.recordId);
    state.currentRecord = state.records.find((item) => item.id === recordId);
    state.currentResponse = await getRecordResponse(recordId);
    render();
  });
  els.favoriteList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-record-id]");
    if (!button) return;
    const recordId = Number(button.dataset.recordId);
    const favorite = state.favorites.find((item) => item.id === recordId);
    if (favorite) {
      await selectConversation(favorite.conversationId);
      state.currentRecord = state.records.find((item) => item.id === recordId);
      state.currentResponse = await getRecordResponse(recordId);
      render();
    }
  });
}

boot();
