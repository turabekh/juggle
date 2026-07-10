<template>
  <q-layout view="hHh lpR fFf">
    <q-header class="jg-header">
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
            :to="{ name: 'bookings' }"
            label="My bookings"
            class="jg-nav__link"
          />
        </nav>

        <div class="jg-header__actions">
          <q-btn
            flat
            round
            icon="shopping_bag"
            :to="{ name: 'cart' }"
            aria-label="Cart"
            class="jg-nav__link"
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
                  <q-item clickable v-close-popup :to="{ name: 'account' }">
                    <q-item-section avatar><q-icon name="face" /></q-item-section>
                    <q-item-section>My kids</q-item-section>
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
            class="jg-signin"
          />
        </div>
      </div>
    </q-header>

    <q-page-container>
      <router-view />
    </q-page-container>

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
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useCartStore } from '@/stores/cart'

const auth = useAuthStore()
const cart = useCartStore()
const router = useRouter()

const displayName = computed(() => auth.user?.full_name || auth.user?.email?.split('@')[0] || 'You')
const initials = computed(() => displayName.value.slice(0, 1).toUpperCase())

function signOut(): void {
  auth.logout()
  router.push({ name: 'discover' })
}
</script>

<style scoped>
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
@media (max-width: 599px) {
  .jg-footer__inner { flex-direction: column; gap: 4px; }
}
</style>
