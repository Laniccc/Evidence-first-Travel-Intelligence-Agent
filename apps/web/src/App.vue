<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { DIRECT_AGENT } from './api/client'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const auth = useAuthStore()
const { token } = storeToRefs(auth)

function logout() {
  auth.logout()
  router.push('/')
}
</script>

<template>
  <div class="app">
    <nav class="navbar">
      <div class="nav-brand" @click="router.push('/')">Deep Research Agent</div>
      <div class="nav-actions">
        <router-link to="/" class="nav-link">Home</router-link>
        <template v-if="!DIRECT_AGENT">
          <template v-if="token">
            <span class="nav-link" @click="logout">Logout</span>
          </template>
          <template v-else>
            <router-link to="/login" class="nav-link">Login</router-link>
          </template>
        </template>
      </div>
    </nav>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style>
:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --border: #2a2d3a;
  --text: #e1e4ed;
  --text-muted: #8b8fa3;
  --accent: #6366f1;
  --accent-hover: #818cf8;
  --success: #22c55e;
  --warning: #f59e0b;
  --danger: #ef4444;
  --radius: 8px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: Inter, system-ui, sans-serif; }
.app { min-height: 100vh; display: flex; flex-direction: column; }
.navbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; height: 56px; background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.nav-brand { font-size: 18px; font-weight: 700; cursor: pointer; color: var(--accent); }
.nav-actions { display: flex; gap: 16px; align-items: center; }
.nav-link { color: var(--text-muted); text-decoration: none; cursor: pointer; font-size: 14px; }
.nav-link:hover, .nav-link.router-link-active { color: var(--text); }
.main-content { flex: 1; padding: 32px 24px; max-width: 900px; margin: 0 auto; width: 100%; }
</style>
