<script setup lang="ts">
import { computed, ref } from 'vue'
import api, { DIRECT_AGENT, RESEARCH_QUERY_PATH } from '../api/client'

const query = ref('')
const loading = ref(false)
const result = ref<any>(null)
const phases = ref<string[]>([])
const error = ref('')

const PHASE_NAMES = ['planning', 'knowledge_retrieval', 'evidence_acquisition', 'evidence_extraction', 'synthesis', 'knowledge_upsert']

const report = computed(() => result.value?.report || null)
const hasReport = computed(() => Boolean(report.value))
const statusLabel = computed(() => (result.value?.status || '').replace(/_/g, ' '))

function formatError(e: any) {
  const detail = e.response?.data?.detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item: any) => item.msg || String(item)).join('; ')
  }
  if (typeof detail === 'string') return detail
  return e.response?.data?.message || e.message || 'Request failed'
}

async function submit() {
  const trimmed = query.value.trim()
  if (trimmed.length < 10) {
    error.value = 'Please enter at least 10 characters.'
    return
  }

  loading.value = true
  error.value = ''
  result.value = null
  phases.value = []

  try {
    const { data } = await api.post(RESEARCH_QUERY_PATH, { query: trimmed })
    result.value = data
    phases.value = data.phases_completed || []
  } catch (e: any) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="home">
    <div class="header-row">
      <div>
        <h1>Deep Research Agent</h1>
        <p class="subtitle">Ask a research question and get an evidence-first report with citations.</p>
      </div>
      <span v-if="DIRECT_AGENT" class="mode-badge">Direct Agent</span>
    </div>

    <div class="query-box">
      <textarea v-model="query" placeholder="e.g. What are the key trends in AI agents in 2025?"
        rows="3" @keydown.ctrl.enter="submit()" :disabled="loading" />
      <button @click="submit()" :disabled="loading || query.trim().length < 10">
        {{ loading ? 'Researching...' : 'Research' }}
      </button>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="loading" class="thinking">
      <div class="spinner" />
      <div class="phase-list">
        <div v-for="p in PHASE_NAMES" :key="p" class="phase">
          {{ p.replace(/_/g, ' ') }}
        </div>
      </div>
    </div>

    <div v-if="result" class="status-panel" :class="'status-' + result.status">
      <strong>{{ statusLabel || 'unknown' }}</strong>
      <span v-if="result.message">{{ result.message }}</span>
      <span v-else-if="result.errors?.length">{{ result.errors[0] }}</span>
    </div>

    <div v-if="hasReport" class="report">
      <h2>{{ report.title || 'Research Report' }}</h2>
      <div class="meta">
        <span class="badge">{{ result.evidence_count || 0 }} sources</span>
        <span class="badge">{{ result.phases_completed?.length || 0 }}/6 phases</span>
      </div>

      <section v-if="report.summary">
        <h3>Summary</h3>
        <p>{{ report.summary }}</p>
      </section>

      <section v-if="report.sections?.length">
        <h3>Findings</h3>
        <div v-for="s in report.sections" :key="s.heading || s.type" class="finding">
          <h4>{{ s.heading || s.type }}</h4>
          <p>{{ s.content }}</p>
        </div>
      </section>

      <section v-if="report.citations?.length">
        <h3>Sources ({{ report.citations.length }})</h3>
        <div v-for="c in report.citations" :key="c.id" class="citation">
          <a :href="c.url" target="_blank" rel="noreferrer">[{{ c.id }}] {{ c.title || c.url }}</a>
          <span class="tier" :class="'tier-' + (c.tier || 3)">T{{ c.tier || 3 }}</span>
        </div>
      </section>

      <section v-if="report.limitations?.length">
        <h3>Limitations</h3>
        <ul>
          <li v-for="l in report.limitations" :key="l">{{ l }}</li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
.home { max-width: 800px; }
.header-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
h1 { font-size: 28px; margin-bottom: 8px; }
.subtitle { color: var(--text-muted); line-height: 1.5; }
.mode-badge { flex: 0 0 auto; padding: 4px 10px; background: rgba(34,197,94,0.15); color: var(--success); border-radius: 999px; font-size: 12px; }

.query-box { display: flex; gap: 12px; margin-bottom: 24px; }
textarea {
  flex: 1; min-height: 92px; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); color: var(--text); font: inherit; resize: vertical;
}
textarea:focus { outline: none; border-color: var(--accent); }
button {
  align-self: stretch; min-width: 124px; padding: 12px 24px; background: var(--accent); color: white;
  border: none; border-radius: var(--radius); cursor: pointer; font: inherit; font-weight: 600;
}
button:disabled { opacity: 0.5; cursor: not-allowed; }
button:hover:not(:disabled) { background: var(--accent-hover); }

.error { padding: 12px; background: rgba(239,68,68,0.1); border: 1px solid var(--danger); border-radius: var(--radius); margin-bottom: 16px; }

.thinking, .status-panel, .report { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
.thinking { padding: 20px; }
.spinner { width: 40px; height: 40px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
.phase-list { display: flex; flex-wrap: wrap; gap: 8px; }
.phase { padding: 6px 12px; background: var(--bg); border-radius: var(--radius); font-size: 13px; color: var(--text-muted); }

.status-panel { display: flex; align-items: center; gap: 10px; padding: 12px 14px; margin-bottom: 16px; color: var(--text-muted); }
.status-panel strong { color: var(--text); text-transform: capitalize; }
.status-completed { border-color: rgba(34,197,94,0.45); }
.status-insufficient_evidence, .status-clarification_needed { border-color: rgba(245,158,11,0.55); }
.status-error { border-color: rgba(239,68,68,0.65); }

.report { margin-top: 24px; padding: 24px; }
.meta { display: flex; gap: 8px; margin-bottom: 20px; }
.badge { padding: 4px 10px; background: rgba(99,102,241,0.15); color: var(--accent); border-radius: 12px; font-size: 12px; }
section { margin-bottom: 20px; }
h3 { font-size: 16px; margin-bottom: 8px; color: var(--text); }
h4 { font-size: 14px; margin-bottom: 4px; }
.finding { margin-bottom: 12px; }
.finding p, section > p { color: var(--text-muted); line-height: 1.6; white-space: pre-wrap; }
.citation { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.citation a { color: var(--accent-hover); font-size: 14px; text-decoration: none; word-break: break-word; }
.tier { flex: 0 0 auto; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.tier-1 { background: rgba(34,197,94,0.15); color: var(--success); }
.tier-2 { background: rgba(99,102,241,0.15); color: var(--accent); }
.tier-3 { background: rgba(245,158,11,0.15); color: var(--warning); }
ul { padding-left: 20px; }
li { color: var(--text-muted); font-size: 14px; margin-bottom: 4px; }

@media (max-width: 640px) {
  .query-box { flex-direction: column; }
  button { align-self: stretch; }
  .header-row { flex-direction: column; }
}
</style>
