<template>
  <q-layout view="hHh lpR fff">
    <q-header class="jg-header">
      <!-- Impersonation banner — always visible while acting as another user (PRD §10.3). -->
      <div v-if="auth.isImpersonating" class="jg-imp-banner">
        <q-icon name="support_agent" size="18px" />
        <span>
          Support session — acting as <strong>{{ auth.user?.email }}</strong>
          <span class="jg-imp-banner__mode">{{ auth.impersonationMode === 'view_as' ? 'view only' : 'can act' }}</span>
        </span>
        <q-btn dense no-caps flat color="white" label="Exit session" icon="logout" @click="exitImpersonation" />
      </div>

      <div class="jg-header__inner">
        <router-link :to="{ name: 'discover' }" class="jg-brand" aria-label="Juggle home">
          <span class="jg-brand__mark">🤹</span>
          <span class="jg-brand__word">Juggle</span>
        </router-link>

        <nav class="jg-nav gt-xs">
          <q-btn flat no-caps :to="{ name: 'discover' }" label="Discover" class="jg-nav__link" />
          <q-btn
            v-if="auth.isAuthed"
            flat
            no-caps
            :to="{ name: 'planner' }"
            label="Holiday planner"
            class="jg-nav__link"
          />
          <q-btn flat no-caps :to="{ name: 'parties' }" label="Birthday parties" class="jg-nav__link" />
          <q-btn
            v-if="auth.isAuthed"
            flat
            no-caps
            :to="{ name: 'bookings' }"
            label="My bookings"
            class="jg-nav__link"
          />
          <q-btn
            v-if="auth.isAuthed"
            flat
            no-caps
            :to="{ name: 'party-plans' }"
            label="Party votes"
            class="jg-nav__link"
          />
        </nav>

        <div class="jg-header__actions">
          <q-btn
            v-if="auth.isAuthed"
            flat
            round
            icon="notifications"
            :to="{ name: 'notifications' }"
            aria-label="Notifications"
            class="jg-nav__link"
          />
          <!-- Cart and Sign in are tabs on mobile, so the header drops them there
               rather than showing the same destination twice. -->
          <q-btn
            flat
            round
            icon="shopping_bag"
            :to="{ name: 'cart' }"
            aria-label="Cart"
            class="jg-nav__link gt-xs"
          >
            <q-badge v-if="cart.count > 0" color="secondary" floating rounded>
              {{ cart.count }}
            </q-badge>
          </q-btn>

          <template v-if="auth.isAuthed">
            <q-btn flat round class="jg-avatar-btn" aria-label="Account">
              <q-avatar size="34px" color="primary" text-color="white">
                {{ initials }}
              </q-avatar>
              <q-menu anchor="bottom right" self="top right">
                <q-list style="min-width: 180px">
                  <q-item class="q-py-md">
                    <q-item-section>
                      <q-item-label class="text-weight-600">{{ displayName }}</q-item-label>
                      <q-item-label caption>{{ auth.user?.email }}</q-item-label>
                    </q-item-section>
                  </q-item>
                  <q-separator />
                  <q-item clickable v-close-popup :to="{ name: 'bookings' }">
                    <q-item-section avatar><q-icon name="confirmation_number" /></q-item-section>
                    <q-item-section>My bookings</q-item-section>
                  </q-item>
                  <q-item clickable v-close-popup :to="{ name: 'party-plans' }">
                    <q-item-section avatar><q-icon name="how_to_vote" /></q-item-section>
                    <q-item-section>Party votes</q-item-section>
                  </q-item>
                  <q-item clickable v-close-popup :to="{ name: 'account' }">
                    <q-item-section avatar><q-icon name="face" /></q-item-section>
                    <q-item-section>My kids</q-item-section>
                  </q-item>
                  <q-separator />
                  <q-item clickable v-close-popup :to="{ name: 'provider' }">
                    <q-item-section avatar><q-icon name="storefront" /></q-item-section>
                    <q-item-section>
                      <q-item-label>Provider console</q-item-label>
                      <q-item-label caption>Switch to running activities</q-item-label>
                    </q-item-section>
                    <q-item-section side><q-icon name="swap_horiz" size="18px" /></q-item-section>
                  </q-item>
                  <q-item v-if="auth.isAdmin" clickable v-close-popup :to="{ name: 'admin-approvals' }">
                    <q-item-section avatar><q-icon name="admin_panel_settings" /></q-item-section>
                    <q-item-section>Admin console</q-item-section>
                  </q-item>
                  <q-separator />
                  <q-item clickable v-close-popup @click="signOut">
                    <q-item-section avatar><q-icon name="logout" /></q-item-section>
                    <q-item-section>Sign out</q-item-section>
                  </q-item>
                </q-list>
              </q-menu>
            </q-btn>
          </template>
          <q-btn
            v-else
            unelevated
            no-caps
            color="primary"
            label="Sign in"
            :to="{ name: 'login' }"
            class="jg-signin gt-xs"
          />
        </div>
      </div>
    </q-header>

    <q-page-container class="jg-main">
      <router-view />
    </q-page-container>

    <!-- Mobile primary nav. The header's `jg-nav` is `gt-xs`, so without this phones
         have no primary navigation at all — signed-out visitors especially. Pure CSS
         breakpoints (Quasar's `lt-sm`), so it renders correctly under SSR too. -->
    <nav class="jg-tabbar lt-sm" aria-label="Primary">
      <router-link
        v-for="tab in tabs"
        :key="tab.key"
        :to="{ name: tab.route }"
        class="jg-tabbar__item"
        :class="{ 'jg-tabbar__item--on': isActive(tab) }"
        :aria-current="isActive(tab) ? 'page' : undefined"
      >
        <span class="jg-tabbar__icon">
          <q-icon :name="tab.icon" size="23px" />
          <q-badge v-if="tab.badge" color="secondary" floating rounded>{{ tab.badge }}</q-badge>
        </span>
        <span class="jg-tabbar__label">{{ tab.label }}</span>
      </router-link>
    </nav>

    <q-footer class="jg-footer">
      <div class="jg-footer__inner">
        <span>Juggle · Kids' holiday activities in Perth</span>
        <span class="jg-faint">Live availability · Book in minutes</span>
      </div>
    </q-footer>
  </q-layout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useCartStore } from '@/stores/cart'

const auth = useAuthStore()
const cart = useCartStore()
const router = useRouter()
const route = useRoute()

interface Tab {
  key: string
  route: string
  label: string
  icon: string
  /** Route names this tab "owns" — a detail page keeps its parent tab lit. */
  owns: string[]
  badge?: number
}

/** Four or five tabs, the native ceiling. Signed-out visitors get Sign in where a
 *  signed-in parent gets Bookings + Account, so the bar is never a dead end. */
const tabs = computed<Tab[]>(() => {
  const discover: Tab = {
    key: 'discover', route: 'discover', label: 'Discover', icon: 'search',
    owns: ['discover', 'session', 'planner'],
  }
  const parties: Tab = {
    key: 'parties', route: 'parties', label: 'Parties', icon: 'celebration',
    owns: ['parties', 'party-package', 'party-plans', 'party-plan-manage', 'party-quotes'],
  }
  const cartTab: Tab = {
    key: 'cart', route: 'cart', label: 'Cart', icon: 'shopping_bag',
    owns: ['cart', 'checkout'],
    badge: cart.count > 0 ? cart.count : undefined,
  }
  if (!auth.isAuthed) {
    return [
      discover, parties, cartTab,
      { key: 'signin', route: 'login', label: 'Sign in', icon: 'person_outline', owns: ['login', 'signup'] },
    ]
  }
  return [
    discover,
    parties,
    { key: 'bookings', route: 'bookings', label: 'Bookings', icon: 'confirmation_number', owns: ['bookings'] },
    cartTab,
    { key: 'account', route: 'account', label: 'Account', icon: 'person', owns: ['account', 'notifications'] },
  ]
})

/** Explicit matching rather than router-link-active: `discover` is `/`, which is a
 *  prefix of every route, so the built-in active class would light it up everywhere. */
function isActive(tab: Tab): boolean {
  return tab.owns.includes(String(route.name ?? ''))
}

const displayName = computed(() => auth.user?.full_name || auth.user?.email?.split('@')[0] || 'You')
const initials = computed(() => displayName.value.slice(0, 1).toUpperCase())

function signOut(): void {
  auth.logout()
  router.push({ name: 'discover' })
}

async function exitImpersonation(): Promise<void> {
  await auth.exitImpersonation()
  router.push({ name: 'admin-impersonation' })
}
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
.jg-header {
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: saturate(1.4) blur(8px);
  color: var(--jg-ink);
  border-bottom: 1px solid var(--jg-line);
}
.jg-header__inner {
  width: 100%;
  max-width: var(--jg-maxw);
  margin: 0 auto;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.jg-brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: var(--jg-ink);
  font-family: 'Fraunces', serif;
  font-weight: 700;
  font-size: 20px;
}
.jg-brand__mark { font-size: 22px; }
.jg-nav {
  display: flex;
  gap: 2px;
  margin-left: 18px;
}
.jg-nav__link { color: var(--jg-ink-soft); font-weight: 600; }
.jg-header__actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
}
.jg-signin { border-radius: 999px; padding: 4px 18px; }
.jg-footer {
  background: transparent;
  color: var(--jg-ink-soft);
}
.jg-footer__inner {
  max-width: var(--jg-maxw);
  margin: 0 auto;
  padding: 18px 20px;
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

/* --- Mobile bottom tab bar ------------------------------------------------ */
.jg-tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2500; /* above q-footer, below dialogs (6000+) */
  display: flex;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: saturate(1.4) blur(10px);
  border-top: 1px solid var(--jg-line);
  /* Keeps the row 58px tall and lifts it clear of the iOS home indicator. */
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
.jg-tabbar__item {
  flex: 1 1 0;
  min-width: 0;
  height: 58px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  text-decoration: none;
  color: var(--jg-ink-faint);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.01em;
  -webkit-tap-highlight-color: transparent;
  transition: color 0.15s ease;
}
.jg-tabbar__item--on { color: var(--jg-primary); }
.jg-tabbar__icon { position: relative; display: inline-flex; }
.jg-tabbar__label {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* A short bar above the active tab — the usual "you are here" cue, and it survives
   for users who can't distinguish the active tint. */
.jg-tabbar__item--on::before {
  content: '';
  position: absolute;
  top: 0;
  width: 26px;
  height: 3px;
  border-radius: 0 0 3px 3px;
  background: var(--jg-primary);
}
.jg-tabbar__item { position: relative; }

@media (prefers-reduced-motion: reduce) {
  .jg-tabbar__item { transition: none; }
}

@media (max-width: 599px) {
  .jg-footer__inner { flex-direction: column; gap: 4px; }
  /* The footer is a sibling of the page container, not inside it, so padding the
     container alone still leaves the document ending underneath the fixed bar.
     Padding the footer — the last element — is what actually clears it. */
  .jg-footer { padding-bottom: var(--jg-tabbar-h); }
}
</style>
