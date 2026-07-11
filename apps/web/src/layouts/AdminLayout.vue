<template>
  <q-layout view="lHh LpR fff">
    <q-header class="jg-adminhdr">
      <div class="jg-adminhdr__inner">
        <div class="row items-center">
          <span class="jg-adminhdr__mark">🤹</span>
          <span class="jg-adminhdr__title">Juggle&nbsp;<span class="jg-adminhdr__tag">Admin</span></span>
        </div>
        <q-space />
        <q-btn flat no-caps dense icon="open_in_new" label="View site" :to="{ name: 'discover' }" class="jg-muted" />
        <div class="jg-adminhdr__who gt-xs">{{ auth.user?.email }}</div>
        <q-btn flat round dense icon="logout" aria-label="Sign out" @click="signOut" />
      </div>
    </q-header>

    <q-drawer :model-value="true" :width="236" bordered class="jg-adminnav">
      <q-list padding>
        <q-item
          v-for="n in nav"
          :key="n.name"
          clickable
          :to="{ name: n.name }"
          active-class="jg-adminnav__active"
          class="jg-adminnav__item"
        >
          <q-item-section avatar><q-icon :name="n.icon" /></q-item-section>
          <q-item-section>{{ n.label }}</q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const nav = [
  { name: 'admin-approvals', label: 'Approvals', icon: 'verified' },
  { name: 'admin-payouts', label: 'Payouts', icon: 'payments' },
  { name: 'admin-reviews', label: 'Reviews', icon: 'reviews' },
  { name: 'admin-config', label: 'Configuration', icon: 'tune' },
  { name: 'admin-flags', label: 'Feature flags', icon: 'flag' },
  { name: 'admin-audit', label: 'Audit log', icon: 'receipt_long' },
  { name: 'admin-funnel', label: 'Funnel', icon: 'filter_alt' },
  { name: 'admin-operations', label: 'Operations', icon: 'schedule' },
  { name: 'admin-impersonation', label: 'Impersonation', icon: 'support_agent' },
]

function signOut(): void {
  auth.logout()
  router.push({ name: 'discover' })
}
</script>

<style scoped>
.jg-adminhdr {
  background: #fff;
  color: var(--jg-ink);
  border-bottom: 1px solid var(--jg-line);
}
.jg-adminhdr__inner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
}
.jg-adminhdr__mark { font-size: 20px; margin-right: 8px; }
.jg-adminhdr__title { font-family: 'Fraunces', serif; font-weight: 700; font-size: 18px; }
.jg-adminhdr__tag { color: var(--jg-primary); }
.jg-adminhdr__who { font-size: 13px; color: var(--jg-ink-soft); margin: 0 6px; }
.jg-adminnav { background: #fbfcfe; }
.jg-adminnav__item {
  border-radius: 10px;
  margin: 2px 8px;
  color: var(--jg-ink-soft);
  font-weight: 600;
}
.jg-adminnav__active {
  background: var(--jg-primary-tint);
  color: var(--jg-primary);
}
</style>
