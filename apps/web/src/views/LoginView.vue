<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const email = ref('')
const password = ref('')
const isRegister = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  try {
    if (isRegister.value) {
      await auth.register(username.value, email.value, password.value)
    } else {
      await auth.login(username.value, password.value)
    }
    router.push('/')
  } catch (e: any) {
    error.value = e.response?.data?.error || e.message
  }
}
</script>

<template>
  <div class="login">
    <h1>{{ isRegister ? 'Register' : 'Login' }}</h1>
    <form @submit.prevent="submit" class="form">
      <input v-model="username" placeholder="Username" required />
      <input v-if="isRegister" v-model="email" type="email" placeholder="Email" required />
      <input v-model="password" type="password" placeholder="Password" required />
      <div v-if="error" class="error">{{ error }}</div>
      <button type="submit">{{ isRegister ? 'Create Account' : 'Login' }}</button>
      <p class="toggle" @click="isRegister = !isRegister">
        {{ isRegister ? 'Already have an account? Login' : 'New user? Register' }}
      </p>
    </form>
  </div>
</template>

<style scoped>
.login { max-width: 360px; margin: 40px auto; }
h1 { text-align: center; margin-bottom: 24px; }
.form { display: flex; flex-direction: column; gap: 12px; }
input {
  padding: 12px 16px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); color: var(--text); font: inherit;
}
input:focus { outline: none; border-color: var(--accent); }
button {
  padding: 12px; background: var(--accent); color: white; border: none;
  border-radius: var(--radius); cursor: pointer; font: inherit; font-weight: 600; margin-top: 8px;
}
button:hover { background: var(--accent-hover); }
.toggle { text-align: center; color: var(--accent); cursor: pointer; font-size: 14px; }
.error { color: var(--danger); font-size: 14px; }
</style>
