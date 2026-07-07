import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref('')

  async function register(user: string, email: string, pass: string) {
    const { data } = await api.post('/api/auth/register', { username: user, email, password: pass })
    token.value = data.token
    username.value = data.username
    localStorage.setItem('token', data.token)
  }

  async function login(user: string, pass: string) {
    const { data } = await api.post('/api/auth/login', { username: user, password: pass })
    token.value = data.token
    username.value = data.username
    localStorage.setItem('token', data.token)
  }

  function logout() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('token')
  }

  return { token, username, register, login, logout }
})
