/**
 * router/index.ts
 *
 * Manual routes for ./src/pages/*.vue
 */

// Composables
import { createRouter, createWebHistory } from 'vue-router'
import Index from '@/pages/index.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/education',
      component: () => import('@/pages/education.vue'),
    },
    {
      path: '/knowledge',
      component: () => import('@/pages/knowledge.vue'),
    },
    {
      path: '/',
      component: Index,
    },
  ],
})

export default router
