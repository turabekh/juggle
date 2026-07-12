<template>
  <q-page>
    <!-- Hero -->
    <section class="jg-party-hero">
      <div class="jg-party-hero__inner">
        <div class="jg-eyebrow" style="color: #fff; opacity: 0.85">Perth · Birthday parties</div>
        <h1 class="jg-party-hero__title">Book a birthday party 🎉</h1>
        <p class="jg-party-hero__sub">
          Party packages from local providers — pick a date, set your guest count, and
          reserve instantly with a deposit.
        </p>
        <q-btn
          unelevated color="white" text-color="deep-purple-9" no-caps class="q-mt-sm"
          icon="how_to_vote" label="Can't decide? Start a vote"
          :to="{ name: 'party-plans' }"
        />
      </div>
    </section>

    <div class="jg-page">
      <div class="jg-results-head">
        <h2 class="text-h6 q-my-none">
          {{ loading ? 'Loading…' : `${packages.length} ${packages.length === 1 ? 'package' : 'packages'}` }}
        </h2>
      </div>

      <div v-if="loading" class="jg-grid">
        <div v-for="n in 4" :key="n" class="jg-card q-pa-md">
          <q-skeleton type="text" width="50%" />
          <q-skeleton type="text" width="80%" class="q-mt-sm" />
          <q-skeleton type="rect" height="42px" class="q-mt-md" />
        </div>
      </div>

      <div v-else-if="packages.length" class="jg-grid">
        <router-link
          v-for="p in packages"
          :key="p.id"
          :to="{ name: 'party-package', params: { id: p.id } }"
          class="jg-card jg-party-card"
        >
          <div class="jg-party-card__head">
            <div class="jg-party-card__name">{{ p.name }}</div>
            <q-chip v-if="p.outdoor" dense square color="orange-2" text-color="orange-9" label="Outdoor" />
          </div>
          <div class="jg-muted text-caption q-mb-sm">
            {{ p.organisation_name }} · {{ p.venue_name
            }}<template v-if="p.venue_suburb">, {{ p.venue_suburb }}</template>
          </div>
          <p v-if="p.description" class="jg-party-card__desc">{{ p.description }}</p>
          <div class="jg-party-card__meta">
            <span class="jg-party-card__price">{{ money(p.per_head_price_cents) }}</span>
            <span class="jg-muted"> / guest</span>
            <span class="jg-dot">·</span>
            <span class="jg-muted">{{ p.min_headcount }}–{{ p.max_headcount }} guests</span>
          </div>
          <q-btn
            unelevated color="primary" no-caps class="full-width q-mt-md"
            label="View &amp; book" :to="{ name: 'party-package', params: { id: p.id } }"
          />
        </router-link>
      </div>

      <EmptyState
        v-else
        icon="celebration"
        title="No party packages yet"
        subtitle="No providers are offering birthday parties right now — check back soon."
      >
        <q-btn unelevated color="primary" no-caps label="Browse activities" :to="{ name: 'discover' }" />
      </EmptyState>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'

import EmptyState from '@/components/EmptyState.vue'
import { api, apiError } from '@/lib/api'
import { money } from '@/lib/format'
import { useHead } from '@/lib/head'
import type { PartyPackageDetail } from '@/lib/types'

const $q = useQuasar()

useHead(() => ({
  title: 'Kids birthday party venues & packages in Perth | Juggle',
  description:
    'Browse and instant-book birthday party packages from local Perth providers — ' +
    'per-head pricing, pick your date and guest count, reserve with a deposit.',
  canonical: `${window.location.origin}/parties`,
}))

const packages = ref<PartyPackageDetail[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    packages.value = await api.parties.allPackages()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not load party packages') })
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.jg-party-hero {
  background: radial-gradient(120% 140% at 15% 0%, #f0724f 0%, #e0518b 55%, #c73f9f 100%);
  color: #fff;
  padding: 8px 20px 40px;
}
.jg-party-hero__inner {
  max-width: var(--jg-maxw);
  margin: 0 auto;
  padding-top: 34px;
}
.jg-party-hero__title {
  color: #fff;
  font-size: clamp(28px, 5vw, 44px);
  line-height: 1.05;
  margin: 8px 0 6px;
}
.jg-party-hero__sub {
  color: rgba(255, 255, 255, 0.9);
  font-size: 16px;
  margin: 0;
  max-width: 520px;
}
.jg-results-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 26px 0 14px;
}
.jg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px;
}
.jg-party-card {
  display: block;
  padding: 18px;
  text-decoration: none;
  color: var(--jg-ink);
  transition: box-shadow 140ms ease, transform 140ms ease;
}
.jg-party-card:hover { box-shadow: var(--jg-shadow-lg); transform: translateY(-2px); }
.jg-party-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.jg-party-card__name { font-weight: 700; font-size: 17px; }
.jg-party-card__desc {
  color: var(--jg-ink-soft);
  font-size: 14px;
  margin: 0 0 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.jg-party-card__meta { font-size: 14px; }
.jg-party-card__price { font-weight: 700; font-size: 16px; }
.jg-dot { margin: 0 8px; color: var(--jg-line); }
</style>
