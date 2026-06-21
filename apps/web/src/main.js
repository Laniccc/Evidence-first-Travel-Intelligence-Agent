import "./styles.css";
import { buildTravelQueryRequest, getApiBaseUrl, postTravelQuery } from "./api/travel.js";

const THINKING_STEPS = [
  "构建会话上下文…",
  "转写用户问题并生成 TravelTask…",
  "识别区域与信息需求…",
  "选择工具并检索证据…",
  "聚合证据、评分并生成回答…",
  "完成引用与限制检查…",
];

const els = {
  query: document.getElementById("query"),
  submit: document.getElementById("submit"),
  clear: document.getElementById("clear"),
  statusList: document.getElementById("status-list"),
  statusCard: document.getElementById("status-card"),
  outputCard: document.getElementById("output-card"),
  answer: document.getElementById("answer"),
  meta: document.getElementById("meta"),
  limitations: document.getElementById("limitations"),
  limitationsList: document.getElementById("limitations-list"),
  errorBox: document.getElementById("error-box"),
  traceDetail: document.getElementById("trace-detail"),
  evidenceDetail: document.getElementById("evidence-detail"),
  toolsDetail: document.getElementById("tools-detail"),
};

let thinkingTimer = null;
let thinkingIndex = 0;

function selectedParties() {
  return [...document.querySelectorAll('input[name="party"]:checked')].map((n) => n.value);
}

function buildUserContext() {
  const ctx = {};
  const travelDate = document.getElementById("travel-date").value.trim();
  const startLocation = document.getElementById("start-location").value.trim();
  const pace = document.getElementById("pace").value;
  const budget = document.getElementById("budget").value;
  const transport = document.getElementById("transport").value;
  const party = selectedParties();

  if (travelDate) ctx.travel_date = travelDate;
  if (startLocation) ctx.start_location = startLocation;
  if (party.length) ctx.party = party;
  if (pace && pace !== "unknown") ctx.pace = pace;
  if (budget && budget !== "unknown") ctx.budget_level = budget;
  if (transport && transport !== "unknown") ctx.transport_preference = transport;

  const lastPlaces = document.getElementById("last-places").value.trim();
  const lastCity = document.getElementById("last-city").value.trim();
  const lastCountry = document.getElementById("last-country").value.trim();
  if (lastPlaces || lastCity || lastCountry) {
    ctx.conversation_memory = {};
    if (lastPlaces) {
      ctx.conversation_memory.last_places = lastPlaces.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
    }
    if (lastCity) ctx.conversation_memory.last_city = lastCity;
    if (lastCountry) ctx.conversation_memory.last_country = lastCountry;
  }

  return ctx;
}

function confidenceClass(value) {
  if (value >= 0.7) return "conf-high";
  if (value >= 0.4) return "conf-mid";
  return "conf-low";
}

function setLoading(loading) {
  els.submit.disabled = loading;
  els.submit.textContent = loading ? "思考中…" : "发送提问";
}

function clearError() {
  els.errorBox.classList.add("hidden");
  els.errorBox.textContent = "";
}

function showError(message) {
  els.errorBox.textContent = message;
  els.errorBox.classList.remove("hidden");
}

function renderThinkingPlaceholder() {
  els.statusList.innerHTML = "";
  THINKING_STEPS.forEach((step, idx) => {
    const li = document.createElement("li");
    li.dataset.idx = String(idx);
    li.innerHTML = `<span class="dot">${idx === 0 ? '<span class="spinner"></span>' : "○"}</span><span>${step}</span>`;
    if (idx === 0) li.classList.add("active");
    els.statusList.appendChild(li);
  });
}

function advanceThinking() {
  const items = [...els.statusList.querySelectorAll("li")];
  if (!items.length) return;
  items.forEach((li) => {
    li.classList.remove("active");
    if (Number(li.dataset.idx) < thinkingIndex) {
      li.classList.add("done");
      li.querySelector(".dot").textContent = "✓";
    }
  });
  if (thinkingIndex < items.length) {
    items[thinkingIndex].classList.add("active");
    items[thinkingIndex].querySelector(".dot").innerHTML = '<span class="spinner"></span>';
    thinkingIndex += 1;
  }
}

function startThinking() {
  thinkingIndex = 0;
  renderThinkingPlaceholder();
  advanceThinking();
  thinkingTimer = window.setInterval(() => {
    if (thinkingIndex >= THINKING_STEPS.length) return;
    advanceThinking();
  }, 1800);
}

function stopThinking() {
  if (thinkingTimer) {
    window.clearInterval(thinkingTimer);
    thinkingTimer = null;
  }
}

function setStatusSpinner(visible) {
  const spinner = document.getElementById("status-spinner");
  if (spinner) spinner.classList.toggle("hidden", !visible);
}

function renderTrace(steps) {
  setStatusSpinner(false);
  els.statusList.innerHTML = "";
  if (!steps || !steps.length) {
    els.statusList.innerHTML = '<li class="done"><span class="dot">✓</span><span>处理完成（无可见 trace）</span></li>';
    return;
  }
  steps.forEach((step) => {
    const li = document.createElement("li");
    li.classList.add("done");
    li.innerHTML = `<span class="dot">✓</span><span>${escapeHtml(step)}</span>`;
    els.statusList.appendChild(li);
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/** @param {import('./api/types.js').TravelQueryResponse} data */
function renderResponse(data) {
  els.outputCard.classList.remove("hidden");
  els.answer.textContent = data.answer || "（无回答文本）";

  els.meta.innerHTML = "";
  const conf = document.createElement("span");
  conf.className = `badge ${confidenceClass(data.confidence || 0)}`;
  conf.textContent = `置信度 ${((data.confidence || 0) * 100).toFixed(0)}%`;
  els.meta.appendChild(conf);

  if (data.query_id) {
    const q = document.createElement("span");
    q.className = "badge neutral";
    q.textContent = `query_id: ${data.query_id.slice(0, 8)}…`;
    els.meta.appendChild(q);
  }

  if (data.evidence_summary?.length) {
    const e = document.createElement("span");
    e.className = "badge neutral";
    e.textContent = `证据 ${data.evidence_summary.length} 条`;
    els.meta.appendChild(e);
  }

  if (data.tool_traces?.length) {
    const t = document.createElement("span");
    t.className = "badge neutral";
    t.textContent = `工具调用 ${data.tool_traces.length} 次`;
    els.meta.appendChild(t);
  }

  const limits = data.limitations || [];
  if (limits.length) {
    els.limitations.classList.remove("hidden");
    els.limitationsList.innerHTML = limits.map((l) => `<li>${escapeHtml(l)}</li>`).join("");
  } else {
    els.limitations.classList.add("hidden");
    els.limitationsList.innerHTML = "";
  }

  els.traceDetail.textContent = JSON.stringify(data.visible_trace || [], null, 2);
  els.evidenceDetail.textContent = JSON.stringify(
    {
      evidence_summary: data.evidence_summary,
      field_evidence_summary: data.field_evidence_summary,
      citation_check_result: data.citation_check_result,
    },
    null,
    2,
  );
  els.toolsDetail.textContent = JSON.stringify(data.tool_traces || [], null, 2);

  if (data.session_id) {
    localStorage.setItem("travel_agent_session_id", data.session_id);
  }
}

async function submitQuery() {
  const query = els.query.value.trim();
  if (!query) {
    showError("请先输入旅行问题。");
    return;
  }

  clearError();
  setLoading(true);
  els.statusCard.classList.remove("hidden");
  els.outputCard.classList.add("hidden");
  setStatusSpinner(true);
  startThinking();

  const sessionId = localStorage.getItem("travel_agent_session_id");
  const payload = buildTravelQueryRequest(query, buildUserContext(), sessionId);

  try {
    const data = await postTravelQuery(payload);
    stopThinking();
    renderTrace(data.visible_trace);
    renderResponse(data);
  } catch (err) {
    stopThinking();
    renderTrace(["请求失败，请确认 api-java (8080) 与 agent-python (8001) 已启动。"]);
    showError(err.message || String(err));
  } finally {
    setLoading(false);
  }
}

function resetForm() {
  els.query.value = "";
  els.statusCard.classList.add("hidden");
  els.outputCard.classList.add("hidden");
  clearError();
}

function wireHeaderLinks() {
  const base = getApiBaseUrl() || window.location.origin;
  const health = document.getElementById("link-health");
  if (health) health.href = `${base}/health`;
}

els.submit.addEventListener("click", submitQuery);
els.clear.addEventListener("click", resetForm);

els.query.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    submitQuery();
  }
});

wireHeaderLinks();
