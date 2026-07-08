import { createRouter, createWebHistory } from 'vue-router'
import { DIRECT_AGENT } from '../api/client'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../views/HomeView.vue'), meta: { requiresAuth: true } },
    { path: '/login', component: () => import('../views/LoginView.vue') },
  ],
})

router.beforeEach((to, _from) => {
  const token = localStorage.getItem('token')
  if (!DIRECT_AGENT && to.meta.requiresAuth && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})

export default router
