import axios from 'axios'

const normalizeBaseUrl = (value: string | undefined) => (value || '').replace(/\/$/, '')

export const DIRECT_AGENT = import.meta.env.VITE_DIRECT_AGENT === 'true'
export const API_BASE_URL = normalizeBaseUrl(
  DIRECT_AGENT
    ? import.meta.env.VITE_AGENT_BASE_URL || 'http://127.0.0.1:8001'
    : import.meta.env.VITE_API_BASE_URL
)
export const RESEARCH_QUERY_PATH = DIRECT_AGENT ? '/agent/query' : '/api/research/query'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: Number(import.meta.env.VITE_QUERY_TIMEOUT_MS || 300000),
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (!DIRECT_AGENT && token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  r => r,
  err => {
    if (DIRECT_AGENT) return Promise.reject(err)

    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    if (err.response?.status === 403) {
      const token = localStorage.getItem('token')
      if (!token) {
        window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname)
        return Promise.reject(new Error('Please login first'))
      }
      localStorage.removeItem('token')
      window.location.href = '/login'
      return Promise.reject(new Error('Session expired. Please login again.'))
    }
    return Promise.reject(err)
  }
)

export default api
