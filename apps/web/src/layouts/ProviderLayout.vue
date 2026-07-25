<template>
  <q-layout view="lHh LpR fff">
    <q-header class="jg-provhdr">
      <!-- Impersonation banner — always visible while acting as another user (INV-10). -->
      <div v-if="auth.isImpersonating" class="jg-imp-banner">
        <q-icon name="support_agent" size="18px" />
        <span>
          Support session — acting as <strong>{{ auth.user?.email }}</strong>
          <span class="jg-imp-banner__mode">{{
            auth.impersonationMode === 'view_as' ? 'view only' : 'can act'
          }}</span>
        </span>
        <q-btn dense no-caps flat color="white" label="Exit session" icon="logout" @click="exitImpersonation" />
      </div>

      <div class="jg-provhdr__inner">
        <q-btn
          flat dense round icon="menu" class="lt-md"
          aria-label="Menu" @click="drawer = !drawer"
        />
        <div class="row items-center no-wrap">
          <span class="jg-provhdr__mark">🤹</span>
          <span class="jg-provhdr__title">Juggle&nbsp;<span class="jg-provhdr__tag">for providers</span></span>
        </div>
        <q-space />
        <q-btn
          flat
          no-caps
          dense
          icon="storefront"
          label="Parent site"
          :to="{ name: 'discover' }"
          class="jg-muted gt-xs"
        />
        <q-btn
          v-if="auth.isAdmin"
          flat
          no-caps
          dense
          icon="admin_panel_settings"
          label="Admin"
          :to="{ name: 'admin-approvals' }"
          class="jg-muted gt-xs"
        />
        <div class="jg-provhdr__who gt-xs">{{ auth.user?.email }}</div>
        <q-btn flat round dense icon="logout" aria-label="Sign out" @click="signOut" />
      </div>
    </q-header>

    <!-- `show-if-above` keeps it pinned open on desktop and turns it into a
         dismissable overlay on phones. It was previously `:model-value="true"`,
         which meant the overlay covered the console with no way to close it. -->
    <q-drawer v-model="drawer" show-if-above :width="248" bordered class="jg-provnav">
      <q-list padding>
        <q-item
          clickable
          :to="{ name: 'provider' }"
          exact
          active-class="jg-provnav__active"
          class="jg-provnav__item"
          @click="closeOnMobile"
        >
          <q-item-section avatar><q-icon name="dashboard" /></q-item-section>
          <q-item-section>Dashboard</q-item-section>
        </q-item>

        <q-item-label header class="jg-provnav__header">Organisations</q-item-label>

        <q-item
          v-for="org in orgs"
          :key="org.id"
          clickable
          :to="{ name: 'provider-org', params: { id: org.id } }"
          active-class="jg-provnav__active"
          class="jg-provnav__item"
          @click="closeOnMobile"
        >
          <q-item-section avatar>
            <q-avatar size="26px" color="primary" text-color="white" class="jg-provnav__orgmark">
              {{ org.name.slice(0, 1).toUpperCase() }}
            </q-avatar>
          </q-item-section>
          <q-item-section>
            <q-item-label lines="1">{{ org.name }}</q-item-label>
            <q-item-label caption>{{ org.status }}</q-item-label>
          </q-item-section>
        </q-item>

        <div v-if="!loading && !orgs.length" class="jg-provnav__empty">
          No organisations yet.
        </div>

        <q-item
          clickable
          :to="{ name: 'provider' }"
          class="jg-provnav__item jg-provnav__new"
          @click="closeOnMobile"
        >
          <q-item-section avatar><q-icon name="add" /></q-item-section>
          <q-item-section>New organisation</q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <q-page-container>
      <router-view @orgs-changed="loadOrgs" />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { Org } from '@/lib/types'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const $q = useQuasar()

const orgs = ref<Org[]>([])
const loading = ref(true)
/** Only consulted below the drawer breakpoint — `show-if-above` pins it open on desktop. */
const drawer = ref(false)

// On a phone the drawer is an overlay covering the page, so picking a destination
// has to dismiss it; otherwise you navigate and still can't see where you landed.
// Closing on tap (not only on route change) also covers tapping the page you're
// already on, which is a no-op navigation but should still get you out of the way.
function closeOnMobile(): void {
  if ($q.screen.lt.md) drawer.value = false
}
watch(() => route.fullPath, closeOnMobile)

async function loadOrgs(): Promise<void> {
  loading.value = true
  try {
    orgs.value = await api.org.mine()
  } catch {
    orgs.value = []
  } finally {
    loading.value = false
  }
}

function signOut(): void {
  auth.logout()
  router.push({ name: 'discover' })
}

async function exitImpersonation(): Promise<void> {
  await auth.exitImpersonation()
  router.push({ name: 'admin-impersonation' })
}

onMounted(loadOrgs)
</script>

<style scoped>
.jg-imp-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: #1e2233;
  color: #fff;
  font-size: 13.5px;
  font-weight: 500;
  padding: 6px 16px;
}
.jg-imp-banner__mode {
  margin-left: 8px;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  font-size: 12px;
  font-weight: 600;
}
.jg-provhdr {
  background: #fff;
  color: var(--jg-ink);
  border-bottom: 1px solid var(--jg-line);
}
.jg-provhdr__inner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
}
.jg-provhdr__mark { font-size: 20px; margin-right: 8px; }
.jg-provhdr__title { font-family: 'Fraunces', serif; font-weight: 700; font-size: 18px; }
.jg-provhdr__tag { color: var(--jg-primary); }
.jg-provhdr__who { font-size: 13px; color: var(--jg-ink-soft); margin: 0 6px; }
.jg-provnav { background: #fbfcfe; }
.jg-provnav__item {
  border-radius: 10px;
  margin: 2px 8px;
  color: var(--jg-ink-soft);
  font-weight: 600;
}
.jg-provnav__active {
  background: var(--jg-primary-tint);
  color: var(--jg-primary);
}
.jg-provnav__header {
  color: var(--jg-ink-soft);
  font-weight: 700;
  letter-spacing: 0.02em;
  padding-top: 14px;
}
.jg-provnav__orgmark { font-size: 12px; font-weight: 700; }
.jg-provnav__empty {
  padding: 4px 20px 8px;
  font-size: 13px;
  color: var(--jg-ink-soft);
}
.jg-provnav__new { color: var(--jg-primary); }
</style>
