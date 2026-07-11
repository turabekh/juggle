import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', name: 'discover', component: () => import('@/pages/DiscoverPage.vue') },
        {
          path: 'sessions/:id',
          name: 'session',
          component: () => import('@/pages/SessionDetailPage.vue'),
          props: true,
        },
        { path: 'cart', name: 'cart', component: () => import('@/pages/CartPage.vue') },
        {
          path: 'checkout',
          name: 'checkout',
          component: () => import('@/pages/CheckoutPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'bookings',
          name: 'bookings',
          component: () => import('@/pages/BookingsPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'account',
          name: 'account',
          component: () => import('@/pages/AccountPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'notifications',
          name: 'notifications',
          component: () => import('@/pages/NotificationsPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'provider',
          name: 'provider',
          component: () => import('@/pages/provider/ProviderDashboard.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'provider/orgs/:id',
          name: 'provider-org',
          component: () => import('@/pages/provider/ProviderOrgPage.vue'),
          props: true,
          meta: { requiresAuth: true },
        },
        {
          path: 'provider/programs/:id',
          name: 'provider-program',
          component: () => import('@/pages/provider/ProviderProgramPage.vue'),
          props: true,
          meta: { requiresAuth: true },
        },
      ],
    },
    {
      path: '/admin',
      component: () => import('@/layouts/AdminLayout.vue'),
      meta: { requiresAdmin: true },
      children: [
        { path: '', redirect: { name: 'admin-approvals' } },
        {
          path: 'approvals',
          name: 'admin-approvals',
          component: () => import('@/pages/admin/AdminApprovalsPage.vue'),
        },
        {
          path: 'config',
          name: 'admin-config',
          component: () => import('@/pages/admin/AdminConfigPage.vue'),
        },
        {
          path: 'payouts',
          name: 'admin-payouts',
          component: () => import('@/pages/admin/AdminPayoutsPage.vue'),
        },
        {
          path: 'reviews',
          name: 'admin-reviews',
          component: () => import('@/pages/admin/AdminReviewsPage.vue'),
        },
        {
          path: 'flags',
          name: 'admin-flags',
          component: () => import('@/pages/admin/AdminFlagsPage.vue'),
        },
        {
          path: 'audit',
          name: 'admin-audit',
          component: () => import('@/pages/admin/AdminAuditPage.vue'),
        },
        {
          path: 'impersonation',
          name: 'admin-impersonation',
          component: () => import('@/pages/admin/AdminImpersonationPage.vue'),
        },
      ],
    },
    { path: '/login', name: 'login', component: () => import('@/pages/LoginPage.vue') },
    { path: '/signup', name: 'signup', component: () => import('@/pages/SignupPage.vue') },
    {
      path: '/:pathMatch(.*)*',
      name: 'notfound',
      component: () => import('@/pages/NotFoundPage.vue'),
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.restore()
  if ((to.meta.requiresAuth || to.meta.requiresAdmin) && !auth.isAuthed) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'discover' }
  }
  return true
})

export default router
