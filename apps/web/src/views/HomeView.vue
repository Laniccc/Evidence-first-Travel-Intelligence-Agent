<script setup lang="ts">
import { ref } from 'vue'
import api from '../api/client'

const query = ref('')
const loading = ref(false)
const result = ref<any>(null)
const phases = ref<string[]>([])
const error = ref('')

const PHASE_NAMES = ['planning','knowledge_retrieval','evidence_acquisition','evidence_extraction','synthesis','knowledge_upsert']

async function submit() {
  if (!query.value.trim()) return
  loading.value = true
  error.value = ''
  result.value = null
  phases.value = []

  try {
    const { data } = await api.post('/api/research/query', { query: query.value })
    result.value = data
    phases.value = data.phases_completed || []
  } catch (e: any) {
    error.value = e.response?.data?.message || e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="home">
    <h1>Deep Research Agent</h1>
    <p class="subtitle">Ask any research question. The agent searches the web, reads pages, cross-references facts, and produces a cited report.</p>

    <div class="query-box">
      <textarea v-model="query" placeholder="e.g. What are the key trends in AI agents in 2025?"
        rows="3" @keydown.ctrl.enter="submit()" :disabled="loading" />
      <button @click="submit()" :disabled="loading || !query.trim()">
        {{ loading ? 'Researching...' : 'Research' }}
      </button>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="loading" class="thinking">
      <div class="spinner" />
      <div class="phase-list">
        <div v-for="p in PHASE_NAMES" :key="p" class="phase" :class="{ active: phases.includes(p), done: phases.includes(p) }">
          {{ p.replace(/_/g, ' ') }}
          <span v-if="phases.includes(p)">✓</span>
          <span v-else-if="phases.length >= PHASE_NAMES.indexOf(p)">...</span>
        </div>
      </div>
    </div>

    <div v-if="result && result.status === 'completed'" class="report">
      <h2>{{ result.report?.title || 'Research Report' }}</h2>
      <div class="meta">
        <span class="badge">{{ result.evidence_count }} sources</span>
        <span class="badge">{{ result.phases_completed?.length || 0 }}/6 phases</span>
      </div>

      <section v-if="result.report?.summary">
        <h3>Summary</h3>
        <p>{{ result.report.summary }}</p>
      </section>

      <section v-if="result.report?.sections?.length">
        <h3>Findings</h3>
        <div v-for="s in result.report.sections" :key="s.heading" class="finding">
          <h4>{{ s.heading }}</h4>
          <p>{{ s.content }}</p>
        </div>
      </section>

      <section v-if="result.report?.citations?.length">
        <h3>Sources ({{ result.report.citations.length }})</h3>
        <div v-for="c in result.report.citations" :key="c.id" class="citation">
          <a :href="c.url" target="_blank">[{{ c.id }}] {{ c.title }}</a>
          <span class="tier" :class="'tier-' + (c.tier || 3)">T{{ c.tier }}</span>
        </div>
      </section>

      <section v-if="result.report?.limitations?.length">
        <h3>Limitations</h3>
        <ul>
          <li v-for="l in result.report.limitations" :key="l">{{ l }}</li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
.home { max-width: 800px; }
h1 { font-size: 28px; margin-bottom: 8px; }
.subtitle { color: var(--text-muted); margin-bottom: 24px; line-height: 1.5; }

.query-box { display: flex; gap: 12px; margin-bottom: 24px; }
textarea {
  flex: 1; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); color: var(--text); font: inherit; resize: vertical;
}
textarea:focus { outline: none; border-color: var(--accent); }
button {
  padding: 12px 24px; background: var(--accent); color: white;
  border: none; border-radius: var(--radius); cursor: pointer; font: inherit; font-weight: 600;
}
button:disabled { opacity: 0.5; cursor: not-allowed; }
button:hover:not(:disabled) { background: var(--accent-hover); }

.error { padding: 12px; background: rgba(239,68,68,0.1); border: 1px solid var(--danger); border-radius: var(--radius); margin-bottom: 16px; }

.thinking { padding: 20px; background: var(--surface); border-radius: var(--radius); }
.spinner { width: 40px; height: 40px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
.phase-list { display: flex; flex-wrap: wrap; gap: 8px; }
.phase { padding: 6px 12px; background: var(--bg); border-radius: var(--radius); font-size: 13px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; }
.phase.active { color: var(--accent); border: 1px solid var(--accent); }
.phase.done { color: var(--success); }

.report { margin-top: 24px; padding: 24px; background: var(--surface); border-radius: var(--radius); }
.meta { display: flex; gap: 8px; margin-bottom: 20px; }
.badge { padding: 4px 10px; background: rgba(99,102,241,0.15); color: var(--accent); border-radius: 12px; font-size: 12px; }
section { margin-bottom: 20px; }
h3 { font-size: 16px; margin-bottom: 8px; color: var(--text); }
h4 { font-size: 14px; margin-bottom: 4px; }
.citation { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; }
.citation a { color: var(--accent-hover); font-size: 14px; text-decoration: none; }
.tier { padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.tier-1 { background: rgba(34,197,94,0.15); color: var(--success); }
.tier-2 { background: rgba(99,102,241,0.15); color: var(--accent); }
.tier-3 { background: rgba(245,158,11,0.15); color: var(--warning); }
ul { padding-left: 20px; }
li { color: var(--text-muted); font-size: 14px; margin-bottom: 4px; }
</style>
